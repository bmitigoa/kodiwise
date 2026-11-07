package com.kodiwise.app

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.firebase.firestore.FirebaseFirestore

class AdminApprovalsActivity : AppCompatActivity() {

    private val db by lazy { FirebaseFirestore.getInstance() }

    private lateinit var rv: RecyclerView
    private lateinit var tvEmpty: TextView
    private lateinit var progress: ProgressBar

    private lateinit var adapter: PendingApprovalAdapter
    private val items = mutableListOf<Property>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_admin_approvals)
        ScreenHeader.bind(this, getString(R.string.title_approvals))

        rv = findViewById(R.id.rvPending)
        tvEmpty = findViewById(R.id.tvEmpty)
        progress = findViewById(R.id.progress)

        adapter = PendingApprovalAdapter(items) { p ->
            val intent = Intent(this, AdminReviewPropertyActivity::class.java)
            intent.putExtra("propertyId", p.id)
            startActivity(intent)
        }

        rv.layoutManager = LinearLayoutManager(this)
        rv.adapter = adapter

        loadPending()
    }

    override fun onResume() {
        super.onResume()
        loadPending()
    }

    private fun loadPending() {
        progress.visibility = View.VISIBLE
        tvEmpty.visibility = View.GONE

        db.collection("properties")
            .whereEqualTo("status", "pending")
            .get()
            .addOnSuccessListener { snap ->
                val list = snap.documents.map { doc ->
                    val p = doc.toObject(Property::class.java) ?: Property()
                    p.id = doc.id
                    p
                }

                adapter.replaceAll(list)
                tvEmpty.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
                progress.visibility = View.GONE
            }
            .addOnFailureListener {
                progress.visibility = View.GONE
                tvEmpty.visibility = View.VISIBLE
            }
    }
}