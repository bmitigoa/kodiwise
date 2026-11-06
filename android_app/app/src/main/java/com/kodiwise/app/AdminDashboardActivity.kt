package com.kodiwise.app

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

class AdminDashboardActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (!AuthManager.isLoggedIn()) {
            startActivity(Intent(this, LoginActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            })
            finish()
            return
        }

        setContentView(R.layout.activity_admin_dashboard)

        // Approve Properties
        findViewById<android.view.View>(R.id.btnApprovals).setOnClickListener {
            startActivity(Intent(this, AdminApprovalsActivity::class.java))
        }

        // Performance Testing (NEW)
        findViewById<android.view.View>(R.id.btnPerformanceTest).setOnClickListener {
            startActivity(Intent(this, PerformanceTestActivity::class.java))
        }

        // Logout
        findViewById<android.view.View>(R.id.btnLogoutAdmin).setOnClickListener {
            AuthManager.signOut()
            Toast.makeText(this, "Logged out", Toast.LENGTH_SHORT).show()
            startActivity(Intent(this, LoginActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            })
            finish()
        }
    }
}