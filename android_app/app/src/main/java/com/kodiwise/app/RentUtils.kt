package com.kodiwise.app

import androidx.annotation.ColorRes
import kotlin.math.abs

object RentUtils {

    // FAIR if within ±10% of predicted
    private const val TOLERANCE = 0.10

    data class BandResult(
        val band: String,      // "LOW" | "FAIR" | "HIGH"
        val ratio: Double      // quoted / predicted
    )

    fun bandFromQuotedVsPredicted(quoted: Double, predicted: Double): BandResult {
        if (predicted <= 0.0 || quoted <= 0.0) return BandResult("FAIR", 1.0)

        val ratio = quoted / predicted
        val diff = abs(ratio - 1.0)

        return when {
            diff <= TOLERANCE -> BandResult("FAIR", ratio)
            ratio > 1.0 -> BandResult("HIGH", ratio)
            else -> BandResult("LOW", ratio)
        }
    }

    // ✅ For TextView.setTextColor()
    @ColorRes
    fun colorForBand(band: String): Int {
        return when (band.uppercase()) {
            "HIGH" -> android.R.color.holo_red_dark
            "LOW" -> android.R.color.holo_orange_dark
            else -> android.R.color.holo_green_dark
        }
    }

    // ✅ NEW: For passing HEX color to ARViewActivity
    fun hexForBand(band: String): String {
        return when (band.uppercase()) {
            "HIGH" -> "#D32F2F"   // red
            "LOW" -> "#F57C00"    // orange
            else -> "#388E3C"     // green
        }
    }
}