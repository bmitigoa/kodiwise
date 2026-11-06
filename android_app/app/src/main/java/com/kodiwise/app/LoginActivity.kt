package com.kodiwise.app

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.firebase.auth.FirebaseAuth

class LoginActivity : AppCompatActivity() {

    private val auth by lazy { FirebaseAuth.getInstance() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)

        val etEmail = findViewById<EditText>(R.id.etEmail)
        val etPassword = findViewById<EditText>(R.id.etPassword)
        val btnLogin = findViewById<Button>(R.id.btnLogin)
        val tvRegister = findViewById<TextView>(R.id.tvRegister)

        // Already logged in -> route
        if (auth.currentUser != null) {
            RoleRouter.route(this)
            return
        }

        tvRegister.setOnClickListener {
            startActivity(Intent(this, RegisterActivity::class.java))
        }

        btnLogin.setOnClickListener {
            val email = etEmail.text.toString().trim()
            val password = etPassword.text.toString().trim()

            if (email.isBlank() || password.isBlank()) {
                Toast.makeText(this, "Enter email and password", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            btnLogin.isEnabled = false

            auth.signInWithEmailAndPassword(email, password)
                .addOnSuccessListener {
                    btnLogin.isEnabled = true
                    Toast.makeText(this, "Login successful ✅", Toast.LENGTH_SHORT).show()
                    RoleRouter.route(this)
                }
                .addOnFailureListener { e ->
                    btnLogin.isEnabled = true
                    Toast.makeText(this, "Login failed: ${e.message}", Toast.LENGTH_LONG).show()
                }
        }
    }
}