package com.kodiwise.app

import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.text.NumberFormat
import java.util.Locale

class PredictionResultActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_prediction_result)
        ScreenHeader.bind(this, "Prediction Result")

        val tvInputs = findViewById<TextView>(R.id.tvInputs)
        val tvPredictedRent = findViewById<TextView>(R.id.tvPredictedRent)
        val tvEstimateNote = findViewById<TextView>(R.id.tvEstimateNote)
        val btnViewInAR = findViewById<Button>(R.id.btnViewInAR)

        val location = intent.getStringExtra("location") ?: ""
        val bedrooms = intent.getIntExtra("bedrooms", 0)
        val bathrooms = intent.getIntExtra("bathrooms", 0)
        val predicted = intent.getDoubleExtra("predicted", 0.0)
        val hasRange = intent.hasExtra("predictedLow") && intent.hasExtra("predictedHigh")
        val predictedLow = intent.getDoubleExtra("predictedLow", 0.0)
        val predictedHigh = intent.getDoubleExtra("predictedHigh", 0.0)

        tvInputs.text = "Location: $location\nBedrooms: $bedrooms\nBathrooms: $bathrooms"

        if (hasRange) {
            tvPredictedRent.text = "Estimated Rent: ${formatKes(predictedLow)} - ${formatKes(predictedHigh)}"
            tvEstimateNote.text = "This is an estimate, not an exact valuation. " +
                "Typical value around ${formatKes(predicted)}."
            tvEstimateNote.visibility = android.view.View.VISIBLE
        } else {
            // Old API fallback: no range available, point estimate only.
            tvPredictedRent.text = "Predicted Rent: ${formatKes(predicted)}"
            tvEstimateNote.text = "This is an estimate, not an exact valuation."
            tvEstimateNote.visibility = android.view.View.VISIBLE
        }

        btnViewInAR.isEnabled = false
        btnViewInAR.text = "AR available for saved properties"
    }

    private fun formatKes(value: Double): String {
        val nf = NumberFormat.getNumberInstance(Locale.US)
        nf.maximumFractionDigits = 0
        return "KES ${nf.format(value)}"
    }
}