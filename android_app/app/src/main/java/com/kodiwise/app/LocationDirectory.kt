package com.kodiwise.app

import android.content.Context
import android.util.Log

/**
 * Cached directory of known neighbourhoods, backing the location
 * AutoCompleteTextView on PredictionFormActivity and PropertyUploadActivity.
 * Persists the last successful GET /locations response in SharedPreferences
 * so the app has a fresh list on next launch without a network round trip,
 * and falls back to a bundled list (the 32 real neighbourhoods behind the
 * model, excluding the internal "Unknown" bucket) if nothing is cached yet
 * and the network call fails.
 */
object LocationDirectory {

    private const val PREFS = "kodiwise_locations"
    private const val KEY_LOCATIONS = "locations"

    val BUNDLED_FALLBACK: List<String> = listOf(
        "Dagoretti", "Donholm", "Embakasi", "Garden Estate", "Gigiri", "Githurai",
        "Hurlingham", "Kahawa", "Kahawa Wendani", "Kahawa West", "Karen", "Kasarani",
        "Kileleshwa", "Kilimani", "Kitisuru", "Langata", "Lavington", "Loresho",
        "Mwiki", "Ngara", "Parklands", "Riverside", "Roysambu", "Runda",
        "South B", "South C", "Spring Valley", "Umoja", "Upperhill", "Utawala",
        "Westlands", "Zimmerman"
    )

    fun getCached(context: Context): List<String> {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val stored = prefs.getStringSet(KEY_LOCATIONS, null)
        return if (!stored.isNullOrEmpty()) stored.sorted() else BUNDLED_FALLBACK
    }

    /** Fetches the live list and caches it. Safe to call from a coroutine;
     * swallows network/API failures and just keeps whatever's already
     * cached (or the bundled fallback). */
    suspend fun refresh(context: Context) {
        try {
            val resp = ApiClient.api.locations()
            val fetched = if (resp.isSuccessful) resp.body()?.locations else null
            if (!fetched.isNullOrEmpty()) {
                context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                    .edit()
                    .putStringSet(KEY_LOCATIONS, fetched.toSet())
                    .apply()
            }
        } catch (e: Exception) {
            Log.w("LocationDirectory", "Failed to refresh locations, using cached/bundled list", e)
        }
    }
}
