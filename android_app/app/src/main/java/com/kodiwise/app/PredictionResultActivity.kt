package com.kodiwise.app

import android.content.res.ColorStateList
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.widget.TextViewCompat
import com.google.android.material.chip.Chip
import java.text.NumberFormat
import java.util.Locale

class PredictionResultActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_prediction_result)
        ScreenHeader.bind(this, getString(R.string.result_title))

        val tvInputs = findViewById<TextView>(R.id.tvInputs)
        val tvHeroValue = findViewById<TextView>(R.id.tvHeroValue)
        val tvPredictedRent = findViewById<TextView>(R.id.tvPredictedRent)
        val tvEstimateNote = findViewById<TextView>(R.id.tvEstimateNote)
        val btnViewInAR = findViewById<Button>(R.id.btnViewInAR)

        // Same extras as before.
        val location = intent.getStringExtra("location") ?: ""
        val bedrooms = intent.getIntExtra("bedrooms", 0)
        val bathrooms = intent.getIntExtra("bathrooms", 0)
        val predicted = intent.getDoubleExtra("predicted", 0.0)
        val hasRange = intent.hasExtra("predictedLow") && intent.hasExtra("predictedHigh")
        val predictedLow = intent.getDoubleExtra("predictedLow", 0.0)
        val predictedHigh = intent.getDoubleExtra("predictedHigh", 0.0)

        tvInputs.text = location
        findViewById<Chip>(R.id.chipBeds).text = resources.getQuantityString(R.plurals.beds, bedrooms, bedrooms)
        findViewById<Chip>(R.id.chipBaths).text = resources.getQuantityString(R.plurals.baths, bathrooms, bathrooms)

        tvHeroValue.text = formatKes(predicted)
        if (hasRange) {
            tvPredictedRent.text = getString(R.string.result_range, formatKes(predictedLow), formatKes(predictedHigh))
            tvEstimateNote.text = getString(R.string.result_note_range)
            showRangeBar(predictedLow, predicted, predictedHigh)
        } else {
            // Old API fallback: no range available, point estimate only.
            tvPredictedRent.text = getString(R.string.result_point_only)
            tvEstimateNote.text = getString(R.string.result_note_point)
            findViewById<View>(R.id.rangeBar).visibility = View.GONE
            findViewById<View>(R.id.rangeLabels).visibility = View.GONE
        }

        // Location confidence as an info chip. A missing extra (older API) or
        // "high" shows nothing.
        val confidence = intent.getStringExtra("locationConfidence")
        PredictionResponse.locationConfidenceHint(confidence)?.let { hint ->
            val chip = findViewById<TextView>(R.id.tvConfidenceHint)
            val (bg, fg) = if (confidence == "low") {
                R.color.kw_secondary_container to R.color.kw_on_secondary_container
            } else {
                R.color.kw_neutral_chip to R.color.kw_on_neutral_chip
            }
            val fgList = ColorStateList.valueOf(ContextCompat.getColor(this, fg))
            chip.text = hint
            chip.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this, bg))
            chip.setTextColor(fgList)
            TextViewCompat.setCompoundDrawableTintList(chip, fgList)
            chip.visibility = View.VISIBLE
        }

        btnViewInAR.isEnabled = false
        btnViewInAR.text = getString(R.string.result_ar_unavailable)
    }

    /** Places the marker along the low..high track at the point estimate. */
    private fun showRangeBar(low: Double, point: Double, high: Double) {
        findViewById<TextView>(R.id.tvRangeLow).text = formatKes(low)
        findViewById<TextView>(R.id.tvRangeHigh).text = formatKes(high)
        val bar = findViewById<View>(R.id.rangeBar)
        val marker = findViewById<View>(R.id.rangeMarker)
        val fraction = if (high > low) ((point - low) / (high - low)).coerceIn(0.0, 1.0) else 0.5
        bar.post {
            val travel = bar.width - marker.width
            val x = (travel * fraction).toFloat()
            marker.translationX = if (bar.layoutDirection == View.LAYOUT_DIRECTION_RTL) -x else x
        }
        bar.contentDescription = getString(R.string.result_range, formatKes(low), formatKes(high))
    }

    private fun formatKes(value: Double): String {
        val nf = NumberFormat.getNumberInstance(Locale.US)
        nf.maximumFractionDigits = 0
        return "KES ${nf.format(value)}"
    }
}
