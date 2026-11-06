package com.kodiwise.app

import android.app.Activity
import android.content.Intent
import android.util.Log
import android.widget.Toast
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore

object RoleRouter {

    private val auth: FirebaseAuth by lazy { FirebaseAuth.getInstance() }
    private val db: FirebaseFirestore by lazy { FirebaseFirestore.getInstance() }

    fun route(activity: Activity) {
        val uid = auth.currentUser?.uid
        if (uid == null) {
            go(activity, LoginActivity::class.java)
            return
        }

        db.collection("users").document(uid).get()
            .addOnSuccessListener { doc ->
                if (!doc.exists()) {
                    Toast.makeText(activity, "User profile missing. Please login again.", Toast.LENGTH_LONG).show()
                    auth.signOut()
                    go(activity, LoginActivity::class.java)
                    return@addOnSuccessListener
                }

                val roleStr = doc.getString("role")?.trim()?.lowercase()
                val target = when (roleStr) {
                    "admin" -> AdminDashboardActivity::class.java
                    "landlord" -> LandlordDashboardActivity::class.java
                    "tenant" -> TenantDashboardActivity::class.java
                    else -> {
                        Toast.makeText(activity, "Role not set. Please login again.", Toast.LENGTH_LONG).show()
                        auth.signOut()
                        LoginActivity::class.java
                    }
                }

                go(activity, target)
            }
            .addOnFailureListener { e ->
                Log.e("ROLE_ROUTER", "Failed to fetch role", e)
                Toast.makeText(activity, "Role load failed: ${e.message}", Toast.LENGTH_LONG).show()
                go(activity, LoginActivity::class.java)
            }
    }

    private fun go(activity: Activity, target: Class<*>) {
        val i = Intent(activity, target).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        activity.startActivity(i)
        activity.finish()
    }
}