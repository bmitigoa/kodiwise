package com.kodiwise.app

import android.os.Bundle
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import coil.load

class FullscreenImageActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_fullscreen_image)
        ScreenHeader.bind(this, "Image Viewer")

        val url = intent.getStringExtra(EXTRA_URL)
            ?: intent.getStringExtra("IMAGE_URL")
            ?: intent.getStringExtra("imageUrl")

        val iv = findViewById<ImageView>(R.id.ivFullImage)
        val tvCounter = findViewById<TextView?>(R.id.tvCounter)

        if (url.isNullOrBlank()) {
            Toast.makeText(this, "Image URL missing", Toast.LENGTH_SHORT).show()
            finish()
            return
        }

        tvCounter?.text = "1 / 1"

        iv.load(url) { crossfade(true) }
    }

    companion object {
        const val EXTRA_URL = "EXTRA_URL"
    }
}