package com.kodiwise.app

import com.google.firebase.auth.FirebaseAuth
import kotlinx.coroutines.tasks.await
import okhttp3.OkHttpClient
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.Header
import retrofit2.http.POST
import java.util.concurrent.TimeUnit

interface ChatApi {
    @POST("chat")
    suspend fun chat(
        @Header("Authorization") bearer: String,
        @Body body: ChatRequestBody
    ): Response<ChatReply>
}

/**
 * Talks to kodiwise-chat. The Gemini key lives only on that service; the app sends the user's
 * Firebase ID token. Message text is never logged here (no body logging on this client).
 */
object ChatClient {
    private val client: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)   // a tool round can take a while on a cold start
            .writeTimeout(20, TimeUnit.SECONDS)
            .build()
    }

    val api: ChatApi by lazy {
        Retrofit.Builder()
            .baseUrl(BuildConfig.CHAT_BASE_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ChatApi::class.java)
    }

    /** Sends the conversation; refreshes the ID token once if the server says it is no longer valid. */
    suspend fun send(body: ChatRequestBody): Response<ChatReply> {
        val user = FirebaseAuth.getInstance().currentUser ?: throw IllegalStateException("not signed in")
        var token = user.getIdToken(false).await().token.orEmpty()
        var resp = api.chat("Bearer $token", body)
        if (resp.code() == 401) {
            token = user.getIdToken(true).await().token.orEmpty()
            resp = api.chat("Bearer $token", body)
        }
        return resp
    }
}
