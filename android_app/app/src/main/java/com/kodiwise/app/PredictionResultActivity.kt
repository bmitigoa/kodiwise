package com.kodiwise.app

import android.content.res.ColorStateList
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.widget.TextViewCompat
import com.google.android.material.chip.Chip
import com.google.gson.Gson
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

        bindWhyCard()

        btnViewInAR.isEnabled = false
        btnViewInAR.text = getString(R.string.result_ar_unavailable)
    }

    /** "Why this estimate": up to 5 factors with +/- KES and a bar each. Hidden if absent. */
    private fun bindWhyCard() {
        val json = intent.getStringExtra("explanationJson") ?: return
        val ex = runCatching { Gson().fromJson(json, Explanation::class.java) }.getOrNull() ?: return
        val factors = WhyEstimate.visible(ex.factors)
        if (factors.isEmpty()) return
        val fractions = WhyEstimate.barFractions(factors)
        val list = findViewById<LinearLayout>(R.id.whyList)
        list.removeAllViews()
        val up = ContextCompat.getColor(this, R.color.kw_primary)
        val down = ContextCompat.getColor(this, R.color.kw_error)
        factors.forEachIndexed { i, f ->
            val row = layoutInflater.inflate(R.layout.item_why_factor, list, false)
            val color = if (WhyEstimate.isUp(f)) up else down
            row.findViewById<TextView>(R.id.tvFactorLabel).text = f.label
            row.findViewById<TextView>(R.id.tvFactorEffect).apply {
                text = WhyEstimate.formatEffect(f.effectKes)
                setTextColor(color)
            }
            row.findViewById<View>(R.id.factorBar).apply {
                backgroundTintList = ColorStateList.valueOf(color)
                layoutParams = (layoutParams as LinearLayout.LayoutParams).apply {
                    width = 0
                    weight = fractions[i]
                }
            }
            row.contentDescription = WhyEstimate.describe(f)
            list.addView(row)
        }
        ex.baselineRentKes?.takeIf { it > 0 }?.let {
            findViewById<TextView>(R.id.tvWhyBaseline).text = getString(R.string.why_baseline, formatKes(it))
        }
        findViewById<View>(R.id.cardWhy).visibility = View.VISIBLE
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
