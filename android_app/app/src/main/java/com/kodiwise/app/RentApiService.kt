package com.kodiwise.app

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

interface RentApiService {

    @GET("health")
    suspend fun health(): Response<Map<String, Any>>

    @GET("locations")
    suspend fun locations(): Response<LocationsResponse>

    @GET("areas-within-budget")
    suspend fun areasWithinBudget(
        @Query("budget_kes") budgetKes: Int,
        @Query("bedrooms") bedrooms: Int,
        @Query("bathrooms") bathrooms: Int,
        @Query("near") near: String? = null,
        @Query("max_km") maxKm: Double? = null
    ): Response<AreasResponse>

    @POST("predict")
    suspend fun predict(@Body req: PredictionRequest): Response<PredictionResponse>
}