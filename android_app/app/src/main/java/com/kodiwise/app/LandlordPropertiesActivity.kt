package com.kodiwise.app

import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.firebase.Timestamp
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext

class LandlordPropertiesActivity : AppCompatActivity() {

    private val db by lazy { FirebaseFirestore.getInstance() }

    private lateinit var rv: RecyclerView
    private lateinit var adapter: LandlordPropertyAdapter
    private lateinit var tvEmpty: TextView
    private lateinit var progress: ProgressBar

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (!AuthManager.isLoggedIn()) {
            Toast.makeText(this, "Please login first", Toast.LENGTH_SHORT).show()
            finish()
            return
        }

        setContentView(R.layout.activity_landlord_properties)
        ScreenHeader.bind(this, getString(R.string.title_my_listings))

        rv = findViewById(R.id.rvLandlordProperties)
        tvEmpty = findViewById(R.id.tvEmpty)
        progress = findViewById(R.id.progress)

        rv.layoutManager = LinearLayoutManager(this)
        rv.setHasFixedSize(true)

        adapter = LandlordPropertyAdapter(
            items = mutableListOf(),
            onClick = { },
            onDelete = { p -> confirmDelete(p.id, p.title) }
        )
        rv.adapter = adapter
    }

    override fun onStart() {
        super.onStart()
        loadMyProperties()
    }

    override fun onResume() {
        super.onResume()
        loadMyProperties()
    }

    private fun loadMyProperties() {
        val uid = AuthManager.uid()
        if (uid == null) {
            Toast.makeText(this, "Please login as landlord", Toast.LENGTH_SHORT).show()
            finish()
            return
        }

        progress.visibility = View.VISIBLE
        tvEmpty.visibility = View.GONE

        db.collection("properties")
            .whereEqualTo("ownerId", uid)
            .get()
            .addOnSuccessListener { snap ->

                val listWithTime = snap.documents.map { doc ->
                    val title = doc.getString("title") ?: ""
                    val location = doc.getString("locationName") ?: ""
                    val bedrooms = (doc.getLong("bedrooms") ?: 0L).toInt()
                    val bathrooms = (doc.getLong("bathrooms") ?: 0L).toInt()

                    val quoted = (
                            doc.getLong("quotedRent")?.toInt()
                                ?: doc.getDouble("quotedRent")?.toInt()
                                ?: doc.getString("quotedRent")?.toIntOrNull()
                                ?: 0
                            )

                    val cover = doc.getString("coverImageUrl") ?: ""
                    val status = doc.getString("status") ?: "pending"
                    val band = doc.getString("rentBand") ?: "FAIR"
                    val adminNotes = doc.getString("adminNotes") ?: ""

                    val createdAtMillis =
                        (doc.getTimestamp("createdAt") ?: Timestamp(0, 0)).toDate().time

                    val property = Property(
                        id = doc.id,
                        title = title,
                        location = location,
                        bedrooms = bedrooms,
                        bathrooms = bathrooms,
                        price = quoted,
                        description = doc.getString("description") ?: "",
                        coverImageUrl = cover,
                        imageUrls = emptyList(),
                        adminNotes = adminNotes,
                        status = status,
                        rentBand = band,
                        predictedRent = doc.getDouble("predictedRent") ?: 0.0,
                        predictedLow = doc.getDouble("predictedLow"),
                        predictedHigh = doc.getDouble("predictedHigh"),
                        locationConfidence = doc.getString("locationConfidence"),
                        rentRatio = doc.getDouble("rentRatio") ?: 1.0,
                        ownerId = doc.getString("ownerId") ?: uid,
                        createdAt = doc.getTimestamp("createdAt"),
                        modelKey = doc.getString("modelKey") ?: ""
                    )

                    Pair(createdAtMillis, property)
                }

                val sorted = listWithTime
                    .sortedByDescending { it.first }
                    .map { it.second }

                adapter.replaceAll(sorted)

                progress.visibility = View.GONE
                tvEmpty.visibility = if (sorted.isEmpty()) View.VISIBLE else View.GONE
            }
            .addOnFailureListener { e ->
                progress.visibility = View.GONE
                Toast.makeText(this, "Failed: ${e.message}", Toast.LENGTH_LONG).show()
                Log.e("LANDLORD_LIST", "loadMyProperties failed", e)
            }
    }

    private fun confirmDelete(propertyId: String, title: String) {
        MaterialAlertDialogBuilder(this)
            .setTitle("Delete property?")
            .setMessage("This will permanently delete:\n$title")
            .setPositiveButton("Delete") { _, _ -> deleteProperty(propertyId) }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun deleteProperty(propertyId: String) {
        lifecycleScope.launch {
            progress.visibility = View.VISIBLE
            try {
                deleteSubcollectionDocs(propertyId)
                db.collection("properties").document(propertyId).delete().await()

                Toast.makeText(this@LandlordPropertiesActivity, "Deleted ✅", Toast.LENGTH_SHORT).show()
                loadMyProperties()

            } catch (e: Exception) {
                progress.visibility = View.GONE
                Toast.makeText(this@LandlordPropertiesActivity, "Delete failed: ${e.message}", Toast.LENGTH_LONG).show()
                Log.e("LANDLORD_DELETE", "deleteProperty failed", e)
            }
        }
    }

    private suspend fun deleteSubcollectionDocs(propertyId: String) = withContext(Dispatchers.IO) {
        val mediaSnap = db.collection("properties")
            .document(propertyId)
            .collection("media")
            .get()
            .await()

        if (mediaSnap.isEmpty) return@withContext

        val batch = db.batch()
        mediaSnap.documents.forEach { d -> batch.delete(d.reference) }
        batch.commit().await()
    }

}