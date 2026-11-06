package com.kodiwise.app

import com.google.gson.Gson
import com.google.gson.GsonBuilder
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {

    // ✅ Cloud Run base url MUST end with "/" — sourced from BuildConfig (see app/build.gradle.kts)
    private val BASE_URL = BuildConfig.API_BASE_URL

    private val gson: Gson by lazy {
        GsonBuilder()
            .setLenient()
            .create()
    }

    private val logger by lazy {
        HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BODY }
    }

    private val client: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .addInterceptor(logger)
            .connectTimeout(25, TimeUnit.SECONDS)
            .readTimeout(25, TimeUnit.SECONDS)
            .writeTimeout(25, TimeUnit.SECONDS)
            .build()
    }

    private val retrofit: Retrofit by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
    }

    val api: RentApiService by lazy {
        retrofit.create(RentApiService::class.java)
    }
}