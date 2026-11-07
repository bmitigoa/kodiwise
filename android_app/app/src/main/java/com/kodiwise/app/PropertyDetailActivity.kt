package com.kodiwise.app

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.Query

class PropertyDetailActivity : AppCompatActivity() {

    private val db by lazy { FirebaseFirestore.getInstance() }

    private lateinit var ivCover: ImageView
    private lateinit var tvStatus: TextView
    private lateinit var tvTitle: TextView
    private lateinit var tvLocation: TextView
    private lateinit var tvMeta: TextView
    private lateinit var tvBand: TextView
    private lateinit var tvDesc: TextView
    private lateinit var rvGallery: RecyclerView
    private lateinit var btnViewAr: Button

    private val mediaItems = mutableListOf<MediaItem>()
    private lateinit var mediaAdapter: MediaAdapter

    private lateinit var propertyId: String

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_property_detail)
        ScreenHeader.bind(this, getString(R.string.title_listing))

        propertyId = intent.getStringExtra("PROPERTY_ID") ?: run {
            Toast.makeText(this, "Property missing", Toast.LENGTH_LONG).show()
            finish()
            return
        }

        ivCover = findViewById(R.id.ivCover)
        tvStatus = findViewById(R.id.tvStatus)
        tvTitle = findViewById(R.id.tvTitle)
        tvLocation = findViewById(R.id.tvLocation)
        tvMeta = findViewById(R.id.tvMeta)
        tvBand = findViewById(R.id.tvBand)
        tvDesc = findViewById(R.id.tvDesc)
        rvGallery = findViewById(R.id.rvGallery)
        btnViewAr = findViewById(R.id.btnViewAr)

        rvGallery.layoutManager = LinearLayoutManager(this, LinearLayoutManager.HORIZONTAL, false)
        mediaAdapter = MediaAdapter(mediaItems) { item ->
            startActivity(
                Intent(this, FullscreenImageActivity::class.java)
                    .putExtra(FullscreenImageActivity.EXTRA_URL, item.url)
            )
        }
        rvGallery.adapter = mediaAdapter

        btnViewAr.setOnClickListener {
            val i = Intent(this, ARViewActivity::class.java)
            i.putExtra("PROPERTY_ID", propertyId)
            startActivity(i)
        }

        loadProperty()
        loadGallery()
    }

    private fun loadProperty() {
        db.collection("properties").document(propertyId).get()
            .addOnSuccessListener { doc ->
                val title = doc.getString("title") ?: "Untitled"
                val loc = doc.getString("locationName") ?: doc.getString("location") ?: "-"
                val statusRaw = doc.getString("status") ?: "approved"
                val statusPretty = statusRaw.replaceFirstChar { it.uppercaseChar() }
                val desc = doc.getString("description") ?: ""

                val bedrooms = (doc.getLong("bedrooms") ?: 0L).toInt()
                val bathrooms = (doc.getLong("bathrooms") ?: 0L).toInt()

                val quoted = (
                        doc.getLong("quotedRent")?.toInt()
                            ?: doc.getDouble("quotedRent")?.toInt()
                            ?: doc.getString("quotedRent")?.toIntOrNull()
                            ?: 0
                        )

                val band = (doc.getString("rentBand") ?: "FAIR").uppercase()
                val cover = doc.getString("coverImageUrl") ?: ""

                ListingCard.bindStatus(tvStatus, statusRaw)
                tvTitle.text = title
                tvLocation.text = loc
                tvMeta.text = statusPretty
                findViewById<TextView>(R.id.tvPrice).text = ListingCard.priceText(this, quoted)
                ListingCard.bindChips(
                    findViewById(R.id.chipBeds), findViewById(R.id.chipBaths), findViewById(R.id.chipSize),
                    bedrooms, bathrooms, doc.getDouble("sq_m")
                )
                ListingCard.bindBand(tvBand, band)
                tvDesc.text = desc.ifBlank { getString(R.string.detail_no_description) }

                ListingCard.bindCover(ivCover, cover)
            }
            .addOnFailureListener { e ->
                Toast.makeText(this, "Load failed: ${e.message}", Toast.LENGTH_LONG).show()
            }
    }

    private fun loadGallery() {
        db.collection("properties")
            .document(propertyId)
            .collection("media")
            .orderBy("createdAt", Query.Direction.ASCENDING)
            .get()
            .addOnSuccessListener { snap ->
                mediaItems.clear()
                snap.documents.forEach { d ->
                    val url = d.getString("url") ?: return@forEach
                    mediaItems.add(MediaItem(url))
                }
                mediaAdapter.notifyDataSetChanged()
                findViewById<android.view.View>(R.id.tvGalleryEmpty).visibility =
                    if (mediaItems.isEmpty()) android.view.View.VISIBLE else android.view.View.GONE
            }
            .addOnFailureListener { e ->
                Toast.makeText(this, "Gallery load failed: ${e.message}", Toast.LENGTH_LONG).show()
            }
    }
}