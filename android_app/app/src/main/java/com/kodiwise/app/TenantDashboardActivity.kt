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

        // Same destinations from the quick-action buttons and the bottom tabs.
        val openPredict = { startActivity(Intent(this, PredictionFormActivity::class.java)) }
        val openArPicker = {
            startActivity(Intent(this, PropertyListActivity::class.java)
                .putExtra(DashboardChrome.EXTRA_AR_HINT, true))
        }
        findViewById<Button>(R.id.btnTenantPredict).setOnClickListener { openPredict() }
        findViewById<Button>(R.id.btnTenantAr).setOnClickListener { openArPicker() }

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

        val btnBrowse = findViewById<Button>(R.id.btnBrowseProperties)
        DashboardChrome.bind(
            this, R.string.role_label_tenant, findViewById(R.id.btnLogout),
            mapOf(
                R.id.nav_browse to { btnBrowse.performClick(); Unit },
                R.id.nav_predict to openPredict,
                R.id.nav_ar to openArPicker,
            )
        )
    }
}