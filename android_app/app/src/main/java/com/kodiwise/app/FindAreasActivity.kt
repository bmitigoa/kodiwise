package com.kodiwise.app

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.android.material.button.MaterialButton
import com.google.android.material.card.MaterialCardView
import com.google.android.material.chip.ChipGroup
import com.google.android.material.progressindicator.LinearProgressIndicator
import com.google.android.material.textfield.MaterialAutoCompleteTextView
import com.google.android.material.textfield.TextInputLayout
import kotlinx.coroutines.launch

/**
 * Rent Assistant, steps 1 and 2: budget and size, then an optional "near this
 * area" filter. Step 3 (results) is AreaResultsActivity. Free and rules-based:
 * it calls the same KodiWise API as the rest of the app.
 */
class FindAreasActivity : AppCompatActivity() {

    private var step = 1

    private lateinit var tilBudget: TextInputLayout
    private lateinit var etBudget: EditText
    private lateinit var etBeds: EditText
    private lateinit var etBaths: EditText
    private lateinit var tilNear: TextInputLayout
    private lateinit var etNear: MaterialAutoCompleteTextView
    private lateinit var chips: ChipGroup
    private lateinit var card1: MaterialCardView
    private lateinit var card2: MaterialCardView
    private lateinit var tvStep: TextView
    private lateinit var stepProgress: LinearProgressIndicator
    private lateinit var btnBack: MaterialButton
    private lateinit var btnNext: MaterialButton

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!AuthManager.isLoggedIn()) {
            finish()
            return
        }
        setContentView(R.layout.activity_find_areas)
        ScreenHeader.bind(this, getString(R.string.title_find_areas))

        tilBudget = findViewById(R.id.tilBudget)
        etBudget = findViewById(R.id.etBudget)
        etBeds = findViewById(R.id.etBeds)
        etBaths = findViewById(R.id.etBaths)
        tilNear = findViewById(R.id.tilNear)
        etNear = findViewById(R.id.etNear)
        chips = findViewById(R.id.chipsDistance)
        card1 = findViewById(R.id.cardStep1)
        card2 = findViewById(R.id.cardStep2)
        tvStep = findViewById(R.id.tvStepLabel)
        stepProgress = findViewById(R.id.stepProgress)
        btnBack = findViewById(R.id.btnStepBack)
        btnNext = findViewById(R.id.btnStepNext)

        FormWidgets.bindStepper(findViewById(R.id.btnBedsMinus), etBeds, findViewById(R.id.btnBedsPlus),
            min = 0, max = AreaAssistant.MAX_BEDS_BATHS)
        FormWidgets.bindStepper(findViewById(R.id.btnBathsMinus), etBaths, findViewById(R.id.btnBathsPlus),
            min = 0, max = AreaAssistant.MAX_BEDS_BATHS)

        val adapter = ArrayAdapter(
            this, android.R.layout.simple_dropdown_item_1line, LocationDirectory.getCached(this).toMutableList()
        )
        etNear.setAdapter(adapter)
        lifecycleScope.launch {
            LocationDirectory.refresh(this@FindAreasActivity)
            adapter.clear()
            adapter.addAll(LocationDirectory.getCached(this@FindAreasActivity))
            adapter.notifyDataSetChanged()
        }

        etBudget.addTextChangedListener(clearError { tilBudget.error = null })
        etNear.addTextChangedListener(clearError { tilNear.error = null })

        findViewById<View>(R.id.btnFairLink).setOnClickListener {
            FairRentSheet.show(this, beds(), baths())
        }
        btnBack.setOnClickListener { goTo(1) }
        btnNext.setOnClickListener { if (step == 1) next() else find() }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (step == 2) goTo(1) else finish()
            }
        })

        step = savedInstanceState?.getInt(KEY_STEP, 1) ?: 1
        goTo(step)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putInt(KEY_STEP, step)
    }

    private fun beds() = (etBeds.text.toString().toIntOrNull() ?: 1).coerceIn(0, AreaAssistant.MAX_BEDS_BATHS)
    private fun baths() = (etBaths.text.toString().toIntOrNull() ?: 1).coerceIn(0, AreaAssistant.MAX_BEDS_BATHS)

    private fun goTo(s: Int) {
        step = s
        card1.visibility = if (s == 1) View.VISIBLE else View.GONE
        card2.visibility = if (s == 2) View.VISIBLE else View.GONE
        btnBack.visibility = if (s == 2) View.VISIBLE else View.GONE
        btnNext.setText(if (s == 1) R.string.finder_next else R.string.finder_find)
        tvStep.text = getString(R.string.finder_step, s)
        stepProgress.setProgressCompat(s, true)
    }

    private fun next() {
        if (AreaAssistant.parseBudget(etBudget.text.toString()) == null) {
            tilBudget.error = getString(R.string.finder_budget_error)
            tilBudget.requestFocus()
            return
        }
        goTo(2)
    }

    private fun find() {
        val budget = AreaAssistant.parseBudget(etBudget.text.toString())
        if (budget == null) {
            goTo(1)
            tilBudget.error = getString(R.string.finder_budget_error)
            return
        }
        val typed = etNear.text.toString().trim()
        var near: String? = null
        if (typed.isNotEmpty()) {
            near = LocationDirectory.match(typed, LocationDirectory.getCached(this))
            if (near == null) {
                tilNear.error = getString(R.string.finder_near_error)
                return
            }
        }
        val km = when (chips.checkedChipId) {
            R.id.chipKm2 -> 2
            R.id.chipKm10 -> 10
            else -> AreaAssistant.DEFAULT_KM
        }
        startActivity(Intent(this, AreaResultsActivity::class.java).apply {
            putExtra(AreaResultsActivity.EXTRA_BUDGET, budget)
            putExtra(AreaResultsActivity.EXTRA_BEDS, beds())
            putExtra(AreaResultsActivity.EXTRA_BATHS, baths())
            if (near != null) {
                putExtra(AreaResultsActivity.EXTRA_NEAR, near)
                putExtra(AreaResultsActivity.EXTRA_KM, km)
            }
        })
    }

    private fun clearError(action: () -> Unit) = object : android.text.TextWatcher {
        override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
        override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
        override fun afterTextChanged(s: android.text.Editable?) = action()
    }

    private companion object {
        const val KEY_STEP = "step"
    }
}
