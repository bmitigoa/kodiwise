package com.kodiwise.app

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

interface RentApiService {

    @GET("health")
    suspend fun health(): Response<Map<String, Any>>

    @GET("locations")
    suspend fun locations(): Response<LocationsResponse>

    @POST("predict")
    suspend fun predict(@Body req: PredictionRequest): Response<PredictionResponse>
}