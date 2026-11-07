package com.kodiwise.app

import android.os.Bundle
import android.widget.Button
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import coil.load

class ARFullscreenImageActivity : AppCompatActivity() {

    private lateinit var ivFullscreen: ImageView
    private lateinit var btnPrevFull: Button
    private lateinit var btnNextFull: Button
    private lateinit var tvCounter: TextView

    private val imageUrls = mutableListOf<String>()
    private var currentIndex = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_ar_fullscreen)
        ScreenHeader.bind(this, getString(R.string.title_gallery))

        ivFullscreen = findViewById(R.id.ivFullscreen)
        btnPrevFull = findViewById(R.id.btnPrevFull)
        btnNextFull = findViewById(R.id.btnNextFull)
        tvCounter = findViewById(R.id.tvCounter)

        val urls = intent.getStringArrayListExtra("IMAGE_URLS") ?: arrayListOf()
        imageUrls.clear()
        imageUrls.addAll(urls)
        currentIndex = intent.getIntExtra("CURRENT_INDEX", 0).coerceAtLeast(0)

        btnPrevFull.setOnClickListener {
            if (imageUrls.isEmpty()) return@setOnClickListener
            currentIndex = if (currentIndex == 0) imageUrls.lastIndex else currentIndex - 1
            showCurrent()
        }

        btnNextFull.setOnClickListener {
            if (imageUrls.isEmpty()) return@setOnClickListener
            currentIndex = if (currentIndex == imageUrls.lastIndex) 0 else currentIndex + 1
            showCurrent()
        }

        showCurrent()
    }

    private fun showCurrent() {
        if (imageUrls.isEmpty()) {
            tvCounter.text = "0 / 0"
            return
        }

        ivFullscreen.load(imageUrls[currentIndex]) {
            crossfade(true)
        }

        tvCounter.text = "${currentIndex + 1} / ${imageUrls.size}"
    }
}