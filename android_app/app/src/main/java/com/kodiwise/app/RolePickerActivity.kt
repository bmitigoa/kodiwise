package com.kodiwise.app

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

class RolePickerActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_role_picker)

        findViewById<Button>(R.id.btnAsTenant).setOnClickListener {
            startActivity(Intent(this, TenantDashboardActivity::class.java))
            finish()
        }

        findViewById<Button>(R.id.btnAsLandlord).setOnClickListener {
            startActivity(Intent(this, LandlordDashboardActivity::class.java))
            finish()
        }

        findViewById<Button>(R.id.btnLogout).setOnClickListener {
            AuthManager.signOut()
            Toast.makeText(this, "Logged out", Toast.LENGTH_SHORT).show()
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
        }
    }
}