package com.kodiwise.app

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.firebase.firestore.FirebaseFirestore

class AdminReviewPropertyActivity : AppCompatActivity() {

    private val db by lazy { FirebaseFirestore.getInstance() }

    private lateinit var rvGallery: RecyclerView
    private lateinit var galleryAdapter: ReviewImagesAdapter

    private lateinit var tvTitle: TextView
    private lateinit var tvLocation: TextView
    private lateinit var tvPrice: TextView
    private lateinit var tvRooms: TextView
    private lateinit var tvDescription: TextView
    private lateinit var tvStatus: TextView
    private lateinit var etNotes: EditText

    private var propertyId: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_admin_review_property)
        ScreenHeader.bind(this, "Review Property")

        propertyId = intent.getStringExtra("propertyId") ?: ""

        rvGallery = findViewById(R.id.rvGallery)
        tvTitle = findViewById(R.id.tvTitle)
        tvLocation = findViewById(R.id.tvLocation)
        tvPrice = findViewById(R.id.tvPrice)
        tvRooms = findViewById(R.id.tvRooms)
        tvDescription = findViewById(R.id.tvDescription)
        tvStatus = findViewById(R.id.tvStatus)
        etNotes = findViewById(R.id.etNotes)

        galleryAdapter = ReviewImagesAdapter(mutableListOf()) { url ->
            val i = Intent(this, FullscreenImageActivity::class.java)
            i.putExtra(FullscreenImageActivity.EXTRA_URL, url)
            startActivity(i)
        }

        rvGallery.layoutManager = LinearLayoutManager(this, LinearLayoutManager.HORIZONTAL, false)
        rvGallery.adapter = galleryAdapter

        findViewById<View>(R.id.btnApprove).setOnClickListener { updateStatus("approved") }
        findViewById<View>(R.id.btnReject).setOnClickListener { updateStatus("rejected") }

        loadProperty()
    }

    private fun loadProperty() {
        if (propertyId.isBlank()) {
            Toast.makeText(this, "Missing property id", Toast.LENGTH_SHORT).show()
            finish()
            return
        }

        db.collection("properties").document(propertyId)
            .get()
            .addOnSuccessListener { doc ->
                val p = doc.toObject(Property::class.java)
                if (p == null) {
                    Toast.makeText(this, "Property not found", Toast.LENGTH_SHORT).show()
                    finish()
                    return@addOnSuccessListener
                }

                p.id = doc.id

                tvTitle.text = p.title.ifBlank { "Untitled" }
                tvLocation.text = p.location.ifBlank { "-" }
                tvPrice.text = "KES ${p.price}"
                tvRooms.text = "${p.bedrooms} Bedrooms • ${p.bathrooms} Bathrooms"
                tvDescription.text = p.description.ifBlank { "-" }
                tvStatus.text = "Status: ${p.prettyStatus()}"

                val galleryUrls: List<String> =
                    if (p.imageUrls.isNotEmpty()) p.imageUrls
                    else if (p.coverImageUrl.isNotBlank()) listOf(p.coverImageUrl)
                    else emptyList()

                galleryAdapter.replaceAll(galleryUrls)
            }
            .addOnFailureListener {
                Toast.makeText(this, "Failed to load property", Toast.LENGTH_SHORT).show()
                finish()
            }
    }

    private fun updateStatus(newStatus: String) {
        val notes = etNotes.text?.toString()?.trim().orEmpty()

        db.collection("properties").document(propertyId)
            .update(
                mapOf(
                    "status" to newStatus,
                    "adminNotes" to notes
                )
            )
            .addOnSuccessListener {
                Toast.makeText(this, "Updated: $newStatus", Toast.LENGTH_SHORT).show()
                finish()
            }
            .addOnFailureListener {
                Toast.makeText(this, "Update failed", Toast.LENGTH_SHORT).show()
            }
    }
}