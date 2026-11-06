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
        val btnViewInAR = findViewById<Button>(R.id.btnViewInAR)

        val location = intent.getStringExtra("location") ?: ""
        val bedrooms = intent.getIntExtra("bedrooms", 0)
        val bathrooms = intent.getIntExtra("bathrooms", 0)
        val predicted = intent.getDoubleExtra("predicted", 0.0)

        tvInputs.text = "Location: $location\nBedrooms: $bedrooms\nBathrooms: $bathrooms"
        tvPredictedRent.text = "Predicted Rent: ${formatKes(predicted)}"

        btnViewInAR.isEnabled = false
        btnViewInAR.text = "AR available for saved properties"
    }

    private fun formatKes(value: Double): String {
        val nf = NumberFormat.getNumberInstance(Locale.US)
        nf.maximumFractionDigits = 0
        return "KES ${nf.format(value)}"
    }
}