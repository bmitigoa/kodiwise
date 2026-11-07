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
        ScreenHeader.bind(this, getString(R.string.title_review))

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

                tvTitle.text = p.title.ifBlank { getString(R.string.listing_untitled) }
                tvLocation.text = p.location.ifBlank { "-" }
                tvPrice.text = ListingCard.priceText(this, p.price)
                tvRooms.text = p.prettyStatus()
                ListingCard.bindChips(
                    findViewById(R.id.chipBeds), findViewById(R.id.chipBaths), findViewById(R.id.chipSize),
                    p.bedrooms, p.bathrooms, p.sqM
                )
                tvDescription.text = p.description.ifBlank { getString(R.string.detail_no_description) }
                ListingCard.bindStatus(tvStatus, p.status)
                ListingCard.bindRange(findViewById(R.id.tvBand), p.price, p.predictedLow, p.predictedHigh, p.locationConfidence)

                val galleryUrls: List<String> =
                    if (p.imageUrls.isNotEmpty()) p.imageUrls
                    else if (p.coverImageUrl.isNotBlank()) listOf(p.coverImageUrl)
                    else emptyList()

                galleryAdapter.replaceAll(galleryUrls)
                findViewById<View>(R.id.tvGalleryEmpty).visibility =
                    if (galleryUrls.isEmpty()) View.VISIBLE else View.GONE
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