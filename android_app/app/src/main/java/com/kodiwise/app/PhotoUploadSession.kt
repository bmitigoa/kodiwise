package com.kodiwise.app

import android.content.Context
import android.net.Uri
import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.storage.FirebaseStorage
import com.google.firebase.storage.StorageMetadata
import kotlinx.coroutines.tasks.await
import java.util.UUID

/** A photo the user has picked but not uploaded yet. [id] becomes the file name. */
data class PendingPhoto(val uri: Uri, val id: String = UUID.randomUUID().toString())

/**
 * Uploads the photos of one listing. Remembers what is already uploaded, so a
 * retry only sends the remaining photos.
 *
 *   run()            upload remaining photos (throws on the first failure)
 *   saveMedia()      write media docs + coverPath for what is uploaded
 *   discardUploads() delete uploaded files (used when the user drops the listing)
 */
class PhotoUploadSession(
    val propertyId: String,
    val photos: List<PendingPhoto>
) {
    private val storage get() = FirebaseStorage.getInstance()
    private val db get() = FirebaseFirestore.getInstance()

    /** photo id -> storage path, for photos that are fully uploaded. */
    private val uploaded = LinkedHashMap<String, String>()

    val uploadedCount: Int get() = uploaded.size
    val remaining: List<PendingPhoto> get() = photos.filter { it.id !in uploaded }

    /** [onProgress] gets (photos finished, total, 0..1 progress of the current photo). */
    suspend fun run(context: Context, onProgress: (Int, Int, Double) -> Unit) {
        for (photo in remaining) {
            onProgress(uploaded.size, photos.size, 0.0)
            val bytes = ImageCompressor.compress(context, photo.uri)
            val path = PhotoRules.photoPath(propertyId, photo.id)
            val meta = StorageMetadata.Builder().setContentType("image/jpeg").build()
            storage.reference.child(path).putBytes(bytes, meta)
                .addOnProgressListener { t ->
                    val f = if (t.totalByteCount > 0) t.bytesTransferred.toDouble() / t.totalByteCount else 0.0
                    onProgress(uploaded.size, photos.size, f)
                }
                .await()
            uploaded[photo.id] = path
        }
        onProgress(uploaded.size, photos.size, 1.0)
    }

    /** Writes one media doc per uploaded photo (in picked order) and sets the cover. */
    suspend fun saveMedia() {
        val ordered = photos.mapNotNull { p -> uploaded[p.id] }
        if (ordered.isEmpty()) return
        val propertyRef = db.collection("properties").document(propertyId)
        val batch = db.batch()
        ordered.forEachIndexed { index, path ->
            batch.set(
                propertyRef.collection("media").document(),
                hashMapOf(
                    "storagePath" to path,
                    "order" to index,
                    "createdAt" to FieldValue.serverTimestamp()
                )
            )
        }
        batch.update(propertyRef, "coverPath", ordered.first())
        batch.commit().await()
    }

    /** Deletes every uploaded file. Failures are ignored: the folder is cleaned on listing delete. */
    suspend fun discardUploads() {
        uploaded.values.forEach { path ->
            try {
                storage.reference.child(path).delete().await()
            } catch (_: Exception) {
            }
        }
        uploaded.clear()
    }
}
