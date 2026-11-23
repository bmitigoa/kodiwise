package com.kodiwise.app

import android.app.Activity
import android.content.Intent
import com.google.gson.Gson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Fetches the full estimate for one area (with "Why this estimate") and opens the result screen. */
object EstimateLauncher {

    /** Request for a plain estimate: only area, bedrooms and bathrooms are known here. */
    fun request(location: String, bedrooms: Int, bathrooms: Int) = PredictionRequest(
        bedroomsNum = bedrooms,
        bathroomsNum = bathrooms,
        locationStd = location,
        propertyTypeStd = "apartment",
        titleClean = "apartment in $location"
    )

    /** @return null on success, or a user-facing error message. */
    suspend fun open(activity: Activity, location: String, bedrooms: Int, bathrooms: Int): String? {
        val body = try {
            val resp = withContext(Dispatchers.IO) { ApiClient.api.predict(request(location, bedrooms, bathrooms)) }
            if (!resp.isSuccessful) return AreaAssistant.errorMessage(resp.code(), resp.errorBody()?.string())
            resp.body()
        } catch (e: Exception) {
            return NETWORK_ERROR
        }
        val pred = body?.predictedRentKes ?: 0.0
        if (pred <= 0) return activity.getString(R.string.area_open_failed)
        activity.startActivity(Intent(activity, PredictionResultActivity::class.java).apply {
            putExtra("location", location)
            putExtra("bedrooms", bedrooms)
            putExtra("bathrooms", bathrooms)
            putExtra("predicted", pred)
            body?.locationConfidence?.let { putExtra("locationConfidence", it) }
            body?.explanation?.takeIf { it.factors.isNotEmpty() }?.let {
                putExtra("explanationJson", Gson().toJson(it))
            }
            if (body?.hasRange() == true) {
                putExtra("predictedLow", body.predictedRentLowKes!!)
                putExtra("predictedHigh", body.predictedRentHighKes!!)
            }
        })
        return null
    }

    const val NETWORK_ERROR = "Network problem. Check your connection and try again."
}
