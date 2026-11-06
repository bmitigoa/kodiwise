package com.kodiwise.app

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

class TenantDashboardActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (!AuthManager.isLoggedIn()) {
            startActivity(
                Intent(this, LoginActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                }
            )
            finish()
            return
        }

        setContentView(R.layout.activity_tenant_dashboard)

        findViewById<Button>(R.id.btnBrowseProperties).setOnClickListener {
            startActivity(Intent(this, PropertyListActivity::class.java))
        }

        findViewById<Button>(R.id.btnLogout).setOnClickListener {
            AuthManager.signOut()
            Toast.makeText(this, "Logged out", Toast.LENGTH_SHORT).show()

            startActivity(
                Intent(this, LoginActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                }
            )
            finish()
        }
    }
}