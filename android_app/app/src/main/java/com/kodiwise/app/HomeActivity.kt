package com.kodiwise.app

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.google.firebase.auth.FirebaseAuth

class HomeActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // ✅ If not logged in → Login
        if (FirebaseAuth.getInstance().currentUser == null) {
            startActivity(android.content.Intent(this, LoginActivity::class.java))
            finish()
            return
        }

        // ✅ Logged in → route by role
        RoleRouter.route(this)
        finish()
    }
}