package com.kodiwise.app

import android.util.Log
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.Query
import com.google.firebase.storage.FirebaseStorage
import com.google.firebase.storage.StorageException
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.tasks.await
import java.util.concurrent.ConcurrentHashMap

/**
 * Reading and deleting listing photos. Photos are stored by path
 * (properties/{id}/photos/{uuid}.jpg); the download URL is resolved when shown,
 * so access always goes through storage.rules and nothing long-lived is saved.
 */
object ListingPhotos {
    private const val TAG = "LISTING_PHOTOS"
    private val urlCache = ConcurrentHashMap<String, String>()

    private val storage get() = FirebaseStorage.getInstance()
    private val db get() = FirebaseFirestore.getInstance()

    /** Download URL for a storage path, or null when it can't be read. */
    suspend fun url(path: String): String? {
        if (path.isBlank()) return null
        urlCache[path]?.let { return it }
        return try {
            storage.reference.child(path).downloadUrl.await().toString().also { urlCache[path] = it }
        } catch (e: Exception) {
            Log.w(TAG, "No URL for $path: ${e.message}")
            null
        }
    }

    /** Photo URLs of a listing in display order (storage photos, else legacy "url" fields). */
    suspend fun forProperty(propertyId: String): List<String> {
        val snap = db.collection("properties").document(propertyId).collection("media")
            .orderBy("order", Query.Direction.ASCENDING)
            .get().await()
        return coroutineScope {
            snap.documents.map { d ->
                async {
                    val path = d.getString("storagePath")
                    if (!path.isNullOrBlank()) url(path) else d.getString("url")
                }
            }.awaitAll().filterNotNull()
        }
    }

    /** Deletes every file under the listing's photos folder. A missing file is fine. */
    suspend fun deleteFiles(propertyId: String) {
        val folder = storage.reference.child(PhotoRules.photosFolder(propertyId))
        val items = try {
            folder.listAll().await().items
        } catch (e: StorageException) {
            if (e.errorCode == StorageException.ERROR_OBJECT_NOT_FOUND) emptyList() else throw e
        }
        items.forEach { ref ->
            try {
                ref.delete().await()
            } catch (e: StorageException) {
                if (e.errorCode != StorageException.ERROR_OBJECT_NOT_FOUND) throw e
            }
            urlCache.remove(ref.path.trimStart('/'))
        }
    }

    /**
     * Deletes a listing: mark it "deleting" (hidden from everyone but the owner),
     * delete photos, delete media docs, delete the doc. Each step is safe to
     * repeat, so if it fails midway the owner can run Delete again to finish.
     */
    suspend fun deleteListing(propertyId: String) {
        val ref = db.collection("properties").document(propertyId)
        ref.update("status", "deleting").await()
        deleteFiles(propertyId)
        val media = ref.collection("media").get().await()
        media.documents.chunked(400).forEach { chunk ->
            val batch = db.batch()
            chunk.forEach { batch.delete(it.reference) }
            batch.commit().await()
        }
        ref.delete().await()
    }
}
