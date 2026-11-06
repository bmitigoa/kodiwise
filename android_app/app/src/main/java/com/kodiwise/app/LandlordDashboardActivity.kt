package com.kodiwise.app

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.widget.Button
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

class LandlordDashboardActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        try {
            if (!AuthManager.isLoggedIn()) {
                startActivity(Intent(this, LoginActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                })
                finish()
                return
            }

            setContentView(R.layout.activity_landlord_dashboard)

            val btnUpload = findViewById<Button?>(R.id.btnUpload)
            val btnMyProps = findViewById<Button?>(R.id.btnMyProperties)
            val btnLogout = findViewById<Button?>(R.id.btnLogout)

            if (btnUpload == null || btnMyProps == null || btnLogout == null) {
                Toast.makeText(
                    this,
                    "❌ Dashboard XML IDs mismatch.\nCheck activity_landlord_dashboard.xml for btnUpload, btnMyProperties, btnLogout",
                    Toast.LENGTH_LONG
                ).show()
                return
            }

            btnUpload.setOnClickListener {
                startActivity(Intent(this, PropertyUploadActivity::class.java))
            }

            btnMyProps.setOnClickListener {
                startActivity(Intent(this, LandlordPropertiesActivity::class.java))
            }

            btnLogout.setOnClickListener {
                AuthManager.signOut()
                Toast.makeText(this, "Logged out", Toast.LENGTH_SHORT).show()
                startActivity(Intent(this, LoginActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                })
                finish()
            }

        } catch (e: Exception) {
            Log.e("LANDLORD_DASH", "Crash in dashboard", e)
            Toast.makeText(this, "Crash: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }
}