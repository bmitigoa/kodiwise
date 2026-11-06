package com.kodiwise.app

import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.textfield.TextInputEditText
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.ListenerRegistration
import com.google.firebase.firestore.Query

class PropertyListActivity : AppCompatActivity() {

    private val db by lazy { FirebaseFirestore.getInstance() }
    private var reg: ListenerRegistration? = null

    private lateinit var rv: RecyclerView
    private lateinit var adapter: BrowsePropertyAdapter
    private lateinit var etSearch: TextInputEditText

    private var lastQuery: String = ""
    private var shownLoadError = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_property_list)
        ScreenHeader.bind(this, "Available Properties")

        etSearch = findViewById(R.id.etSearch)

        rv = findViewById(R.id.rvBrowseProperties)
        rv.layoutManager = LinearLayoutManager(this)
        rv.setHasFixedSize(true)

        adapter = BrowsePropertyAdapter(mutableListOf()) { item ->
            val i = Intent(this, PropertyDetailActivity::class.java)
            i.putExtra("PROPERTY_ID", item.id)
            startActivity(i)
        }
        rv.adapter = adapter

        etSearch.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {}

            override fun beforeTextChanged(
                s: CharSequence?,
                start: Int,
                count: Int,
                after: Int
            ) {
            }

            override fun onTextChanged(
                s: CharSequence?,
                start: Int,
                before: Int,
                count: Int
            ) {
                lastQuery = s?.toString().orEmpty()
                adapter.filter(lastQuery)
            }
        })
    }

    override fun onStart() {
        super.onStart()
        attachListenerNoIndex()
    }

    override fun onStop() {
        super.onStop()
        reg?.remove()
        reg = null
    }

    private fun attachListenerNoIndex() {
        reg?.remove()

        reg = db.collection("properties")
            .orderBy("createdAt", Query.Direction.DESCENDING)
            .addSnapshotListener { snap, e ->

                if (e != null) {
                    if (!shownLoadError) {
                        shownLoadError = true
                        Toast.makeText(this, "Load failed: ${e.message}", Toast.LENGTH_LONG).show()
                    }
                    return@addSnapshotListener
                }

                shownLoadError = false

                val fresh = mutableListOf<Property>()

                snap?.documents?.forEach { doc ->
                    val status = (doc.getString("status") ?: "").trim()
                    if (!status.equals("approved", ignoreCase = true)) return@forEach

                    val p = doc.toObject(Property::class.java)
                    if (p != null) {
                        p.id = doc.id
                        fresh.add(p)
                    }
                }

                adapter.replaceAll(fresh)
                adapter.filter(lastQuery)
            }
    }
}