package com.kodiwise.app

import android.content.Intent
import android.os.Bundle
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore

class RegisterActivity : AppCompatActivity() {

    private val auth by lazy { FirebaseAuth.getInstance() }
    private val db by lazy { FirebaseFirestore.getInstance() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_register)

        // ✅ IDs match the new activity_register.xml
        val etEmail = findViewById<EditText>(R.id.etRegEmail)
        val etPass = findViewById<EditText>(R.id.etRegPassword)
        val etConfirm = findViewById<EditText>(R.id.etRegConfirm)
        val btnRegister = findViewById<Button>(R.id.btnRegister)
        val tvGoLogin = findViewById<TextView>(R.id.tvGoLogin)

        val roleGroup = findViewById<RadioGroup>(R.id.roleGroup)
        val rbTenant = findViewById<RadioButton>(R.id.rbTenant)
        val rbLandlord = findViewById<RadioButton>(R.id.rbLandlord)

        // Default role
        rbTenant.isChecked = true

        tvGoLogin.setOnClickListener {
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
        }

        btnRegister.setOnClickListener {
            val email = etEmail.text.toString().trim()
            val pass = etPass.text.toString().trim()
            val confirm = etConfirm.text.toString().trim()

            if (email.isBlank() || pass.isBlank() || confirm.isBlank()) {
                toast("Fill in all fields")
                return@setOnClickListener
            }

            if (pass.length < 6) {
                toast("Password must be at least 6 characters")
                return@setOnClickListener
            }

            if (pass != confirm) {
                toast("Passwords do not match")
                return@setOnClickListener
            }

            // ✅ Only allow TENANT or LANDLORD registration from app
            val role = if (roleGroup.checkedRadioButtonId == R.id.rbLandlord) {
                UserRole.LANDLORD.key
            } else {
                UserRole.TENANT.key
            }

            setLoading(btnRegister, true)

            auth.createUserWithEmailAndPassword(email, pass)
                .addOnSuccessListener { result ->
                    val uid = result.user?.uid
                    if (uid.isNullOrBlank()) {
                        setLoading(btnRegister, false)
                        toast("Registration failed (no UID)")
                        return@addOnSuccessListener
                    }

                    val userDoc = hashMapOf(
                        "email" to email,
                        "role" to role
                    )

                    // ✅ IMPORTANT: only route AFTER Firestore role doc is saved
                    db.collection("users").document(uid).set(userDoc)
                        .addOnSuccessListener {
                            setLoading(btnRegister, false)
                            toast("Account created ✅")
                            RoleRouter.route(this)
                        }
                        .addOnFailureListener { e ->
                            // ✅ CRITICAL FIX:
                            // If Firestore profile fails, delete the auth user to avoid "profile missing" bugs later
                            auth.currentUser?.delete()
                                ?.addOnCompleteListener {
                                    setLoading(btnRegister, false)
                                    toast("Registration failed: could not save role. Try again. (${e.message})")
                                }
                        }
                }
                .addOnFailureListener { e ->
                    setLoading(btnRegister, false)
                    toast("Registration failed: ${e.message}")
                }
        }
    }

    private fun setLoading(btn: Button, loading: Boolean) {
        btn.isEnabled = !loading
        // ✅ Keep UI consistent with Image 1
        btn.text = if (loading) "Creating..." else "Create Account"
    }

    private fun toast(msg: String) {
        Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
    }
}