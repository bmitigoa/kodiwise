package com.kodiwise.app

import com.google.firebase.auth.FirebaseAuth

object AuthManager {
    private val auth: FirebaseAuth by lazy { FirebaseAuth.getInstance() }

    fun uid(): String? = auth.currentUser?.uid

    fun isLoggedIn(): Boolean = auth.currentUser != null

    fun signOut() {
        auth.signOut()
    }
}