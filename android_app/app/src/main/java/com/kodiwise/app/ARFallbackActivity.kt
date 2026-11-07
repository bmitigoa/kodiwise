package com.kodiwise.app

import android.os.Bundle
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import coil.load
import com.google.firebase.firestore.FirebaseFirestore

class ARFallbackActivity : AppCompatActivity() {

    private val db by lazy { FirebaseFirestore.getInstance() }
    private var propertyId: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_ar_fallback)

        propertyId = intent.getStringExtra("PROPERTY_ID") ?: ""
        if (propertyId.isBlank()) {
            Toast.makeText(this, "Property missing", Toast.LENGTH_LONG).show()
            finish()
            return
        }

        loadProperty()
    }

    private fun loadProperty() {
        db.collection("properties").document(propertyId).get()
            .addOnSuccessListener { doc ->
                val title = doc.getString("title") ?: "Untitled"
                val loc = doc.getString("locationName") ?: doc.getString("location") ?: "-"

                val bedrooms = (doc.getLong("bedrooms") ?: 0L).toInt()
                val bathrooms = (doc.getLong("bathrooms") ?: 0L).toInt()

                val quoted = (doc.getLong("quotedRent")?.toInt()
                    ?: doc.getDouble("quotedRent")?.toInt()
                    ?: doc.getString("quotedRent")?.toIntOrNull()
                    ?: 0)

                val band = (doc.getString("rentBand") ?: "FAIR").uppercase()
                val cover = doc.getString("coverImageUrl") ?: ""

                findViewById<TextView>(R.id.tvFallbackTitle).text = title
                findViewById<TextView>(R.id.tvFallbackLocation).text = loc
                findViewById<TextView>(R.id.tvFallbackMeta).text =
                    "${bedrooms} beds • ${bathrooms} baths • KES $quoted"

                ListingCard.bindBand(findViewById(R.id.tvFallbackBand), band)
                ListingCard.bindCover(findViewById<ImageView>(R.id.ivFallbackCover), cover)
            }
            .addOnFailureListener { e ->
                Toast.makeText(this, "Load failed: ${e.message}", Toast.LENGTH_LONG).show()
                finish()
            }
    }
}