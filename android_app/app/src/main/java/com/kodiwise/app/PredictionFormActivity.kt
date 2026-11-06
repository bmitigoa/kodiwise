package com.kodiwise.app

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class PredictionFormActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_prediction_form)

        val etLocation = findViewById<EditText>(R.id.etPLocation)
        val etBedrooms = findViewById<EditText>(R.id.etPBedrooms)
        val etBathrooms = findViewById<EditText>(R.id.etPBathrooms)
        val btnPredict = findViewById<Button>(R.id.btnPredictNow)

        btnPredict.setOnClickListener {

            val location = etLocation.text.toString().trim()
            val bedroomsStr = etBedrooms.text.toString().trim()
            val bathroomsStr = etBathrooms.text.toString().trim()

            if (location.isBlank() || bedroomsStr.isBlank() || bathroomsStr.isBlank()) {
                Toast.makeText(this, "Please fill in all fields", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            val bedrooms = bedroomsStr.toIntOrNull()
            val bathrooms = bathroomsStr.toIntOrNull()

            if (bedrooms == null || bathrooms == null || bedrooms <= 0 || bathrooms <= 0) {
                Toast.makeText(this, "Enter valid bedrooms/bathrooms", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            val req = PredictionRequest(
                bedroomsNum = bedrooms,
                bathroomsNum = bathrooms,
                locationStd = location,
                propertyTypeStd = "apartment",
                titleClean = "apartment in $location"
            )

            lifecycleScope.launch(Dispatchers.IO) {
                try {
                    val resp = ApiClient.api.predict(req)

                    if (!resp.isSuccessful) {
                        val err = resp.errorBody()?.string()
                        Log.e("PREDICT_FORM", "HTTP ${resp.code()} err=$err")
                        withContext(Dispatchers.Main) {
                            Toast.makeText(
                                this@PredictionFormActivity,
                                "API error ${resp.code()}",
                                Toast.LENGTH_LONG
                            ).show()
                        }
                        return@launch
                    }

                    val pred = resp.body()?.predictedRentKes ?: 0.0

                    withContext(Dispatchers.Main) {
                        if (pred != null && pred > 0) {
                            val i = Intent(this@PredictionFormActivity, PredictionResultActivity::class.java).apply {
                                putExtra("location", location)
                                putExtra("bedrooms", bedrooms)
                                putExtra("bathrooms", bathrooms)
                                putExtra("predicted", pred)
                            }
                            startActivity(i)
                        } else {
                            Toast.makeText(
                                this@PredictionFormActivity,
                                "Prediction unavailable",
                                Toast.LENGTH_LONG
                            ).show()
                        }
                    }

                } catch (e: Exception) {
                    Log.e("PREDICT_FORM", "Network exception", e)
                    withContext(Dispatchers.Main) {
                        Toast.makeText(
                            this@PredictionFormActivity,
                            "Network error: ${e.message}",
                            Toast.LENGTH_LONG
                        ).show()
                    }
                }
            }
        }
    }
}