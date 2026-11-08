package com.kodiwise.app

import android.os.Bundle
import android.util.Log
import android.widget.ArrayAdapter
import android.widget.AutoCompleteTextView
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import java.util.Locale

class PropertyUploadActivity : AppCompatActivity() {

    private val firestore by lazy { FirebaseFirestore.getInstance() }

    // UI
    private lateinit var btnSubmit: Button
    private lateinit var tvUploadStatus: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (!AuthManager.isLoggedIn()) {
            toast("Please login first")
            finish()
            return
        }

        setContentView(R.layout.activity_property_upload)
        ScreenHeader.bind(this, getString(R.string.title_add_listing))

        // Inputs
        val etTitle = findViewById<EditText>(R.id.etTitle)
        val etLocation = findViewById<AutoCompleteTextView>(R.id.etLocation)
        val etBedrooms = findViewById<EditText>(R.id.etBedrooms)
        val etBathrooms = findViewById<EditText>(R.id.etBathrooms)
        val etPrice = findViewById<EditText>(R.id.etPrice)
        val etDescription = findViewById<EditText>(R.id.etDescription)

        // UI
        btnSubmit = findViewById(R.id.btnSubmitUpload)
        tvUploadStatus = findViewById(R.id.tvUploadStatus)

        // Steppers only edit the number fields; validation below is unchanged
        // (it accepts 0 bedrooms, e.g. a bedsitter, so the stepper allows 0).
        FormWidgets.bindStepper(findViewById(R.id.btnBedroomsMinus), etBedrooms, findViewById(R.id.btnBedroomsPlus), min = 0)
        FormWidgets.bindStepper(findViewById(R.id.btnBathroomsMinus), etBathrooms, findViewById(R.id.btnBathroomsPlus), min = 0)

        RealisticPropertyFields.bindCollapse(this)
        RealisticPropertyFields.bindDontKnowSize(this)

        val locationAdapter = ArrayAdapter(
            this, android.R.layout.simple_dropdown_item_1line, LocationDirectory.getCached(this).toMutableList()
        )
        etLocation.setAdapter(locationAdapter)
        val tilLocation = findViewById<com.google.android.material.textfield.TextInputLayout>(R.id.tilLocation)
        etLocation.addTextChangedListener(object : android.text.TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: android.text.Editable?) { tilLocation.error = null }
        })
        lifecycleScope.launch {
            LocationDirectory.refresh(this@PropertyUploadActivity)
            locationAdapter.clear()
            locationAdapter.addAll(LocationDirectory.getCached(this@PropertyUploadActivity))
            locationAdapter.notifyDataSetChanged()
        }

        btnSubmit.setOnClickListener {
            val uid = AuthManager.uid()
            if (uid == null) {
                toast("Please login first")
                return@setOnClickListener
            }

            val title = etTitle.text.toString().trim()
            // Must be one of the /locations neighbourhoods (case-insensitive);
            // saved with its canonical spelling.
            val locationName = LocationDirectory.match(
                etLocation.text.toString(), LocationDirectory.getCached(this)
            ) ?: ""
            val bedrooms = etBedrooms.text.toString().toIntOrNull()
            val bathrooms = etBathrooms.text.toString().toIntOrNull()
            val quotedRent = etPrice.text.toString().toDoubleOrNull()
            val description = etDescription.text.toString().trim()

            if (locationName.isEmpty()) {
                tilLocation.error = getString(R.string.error_location_pick)
                tilLocation.requestFocus()
                return@setOnClickListener
            }

            if (title.isEmpty() || locationName.isEmpty() ||
                bedrooms == null || bathrooms == null ||
                quotedRent == null || description.isEmpty()
            ) {
                toast("Fill all fields correctly")
                return@setOnClickListener
            }

            val realistic = RealisticPropertyFields.read(this)

            lifecycleScope.launch {
                setUploading(true)
                try {
                    tvUploadStatus.text = "Predicting rent (ML)..."

                    val req = PredictionRequest(
                        bedroomsNum = bedrooms,
                        bathroomsNum = bathrooms,
                        locationStd = locationName,
                        propertyTypeStd = "apartment",
                        titleClean = cleanTitle(title),
                        sqM = realistic.sqM,
                        isFurnished = realistic.isFurnished,
                        propertyType = realistic.propertyType,
                        hasGenerator = realistic.hasGenerator,
                        hasBorehole = realistic.hasBorehole,
                        hasCctv = realistic.hasCctv,
                        hasDsq = realistic.hasDsq,
                        hasPlayArea = realistic.hasPlayArea,
                        hasGarden = realistic.hasGarden
                    )

                    val prediction = withContext(Dispatchers.IO) {
                        val resp = ApiClient.api.predict(req)
                        if (!resp.isSuccessful) {
                            val err = resp.errorBody()?.string()
                            throw RuntimeException("API ${resp.code()}: ${err ?: "unknown error"}")
                        }
                        resp.body()
                    }
                    val predictedRent = prediction?.bestValue() ?: 0.0

                    val bandResult = RentUtils.bandFromQuotedVsPredicted(quotedRent, predictedRent)
                    val rentBand = bandResult.band
                    val rentRatio = bandResult.ratio

                    tvUploadStatus.text = "Saving property..."
                    val propertyRef = firestore.collection("properties").document()
                    val propertyId = propertyRef.id

                    val propertyData = hashMapOf<String, Any?>(
                        "title" to title,
                        "locationName" to locationName,
                        "bedrooms" to bedrooms,
                        "bathrooms" to bathrooms,
                        "quotedRent" to quotedRent,
                        "description" to description,

                        "status" to "pending",
                        "ownerId" to uid,
                        "createdAt" to FieldValue.serverTimestamp(),

                        "predictedRent" to predictedRent,
                        // Prediction range + confidence: drive the listing's range badge.
                        "predictedLow" to prediction?.predictedRentLowKes,
                        "predictedHigh" to prediction?.predictedRentHighKes,
                        "locationConfidence" to prediction?.locationConfidence,
                        // Legacy fixed-tolerance band: still written for compatibility,
                        // no longer displayed.
                        "rentBand" to rentBand,
                        "rentRatio" to rentRatio,

                        // Realistic property fields -- same names as
                        // ml.features.RUN_D_FEATURE_SET / the API schema,
                        // so a future retrain can read straight off these
                        // Firestore docs without a field-name mapping step.

                        // AR placeholders
                        "arScale" to 0.4,
                        "arRotationY" to 180
                    )

                    // Realistic fields: amenities stay null when never answered.
                    propertyData.putAll(RealisticPropertyFields.toFirestoreFields(realistic))

                    propertyRef.set(propertyData).await()

                    tvUploadStatus.text = "Done ✅"
                    toast("Uploaded ✅ (Pending Admin Approval)")
                    setResult(RESULT_OK)
                    finish()

                } catch (e: Exception) {
                    Log.e("PROPERTY_UPLOAD", "Upload failed", e)
                    toast("Upload failed: ${e.message}")
                    tvUploadStatus.text = "Upload failed"
                    setUploading(false)
                }
            }
        }
    }

    private fun setUploading(uploading: Boolean) {
        btnSubmit.isEnabled = !uploading
        btnSubmit.setText(if (uploading) R.string.upload_button_busy else R.string.upload_button)
        // The status line starts hidden; once an upload starts it stays visible
        // so its last message ("Upload failed", ...) remains readable.
        if (uploading) tvUploadStatus.visibility = android.view.View.VISIBLE
        findViewById<android.view.View>(R.id.progressUpload).visibility =
            if (uploading) android.view.View.VISIBLE else android.view.View.GONE
    }

    private fun cleanTitle(title: String): String {
        return title.lowercase(Locale.getDefault())
            .replace(Regex("[^a-z0-9\\s]"), " ")
            .replace(Regex("\\s+"), " ")
            .trim()
    }

    private fun toast(msg: String) {
        Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
    }
}