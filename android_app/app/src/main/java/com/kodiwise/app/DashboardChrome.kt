package com.kodiwise.app

import android.view.View
import android.widget.TextView
import androidx.annotation.StringRes
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.android.material.bottomsheet.BottomSheetDialog
import com.google.firebase.auth.FirebaseAuth
import java.util.Calendar

/**
 * Shared dashboard chrome: greeting top app bar, bottom navigation and the
 * profile sheet. Presentation only -- every tab runs the same code as an
 * existing dashboard button, and the profile sheet's "Log out" triggers the
 * dashboard's existing logout button, so no navigation or auth logic lives here.
 */
object DashboardChrome {

    /** PropertyListActivity extra: opened from an "AR" entry point, so show
     *  the "pick a listing to view it in AR" banner. Display only. */
    const val EXTRA_AR_HINT = "com.kodiwise.app.AR_HINT"

    @StringRes
    private fun greetingRes(): Int {
        val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
        return when {
            hour < 12 -> R.string.greeting_morning
            hour < 17 -> R.string.greeting_afternoon
            else -> R.string.greeting_evening
        }
    }

    /**
     * @param tabActions bottom-nav item id -> action (usually an existing
     *   button's performClick). R.id.nav_profile is handled here.
     */
    fun bind(
        activity: AppCompatActivity,
        @StringRes roleLabel: Int,
        logoutButton: View,
        tabActions: Map<Int, () -> Unit>,
    ) {
        val email = FirebaseAuth.getInstance().currentUser?.email
        activity.findViewById<MaterialToolbar>(R.id.toolbar)?.apply {
            title = activity.getString(greetingRes())
            subtitle = email
        }

        val nav = activity.findViewById<BottomNavigationView>(R.id.bottomNav) ?: return
        // The dashboard is the Home tab. Every other tab opens its screen (or
        // the profile sheet) without changing the selection, so Home stays
        // highlighted whenever the dashboard is showing.
        nav.selectedItemId = R.id.nav_home
        nav.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.nav_home -> return@setOnItemSelectedListener true
                R.id.nav_profile -> showProfile(activity, email, roleLabel, logoutButton)
                else -> tabActions[item.itemId]?.invoke()
            }
            false
        }
        nav.setOnItemReselectedListener { /* already on Home */ }
    }

    private fun showProfile(activity: AppCompatActivity, email: String?, @StringRes roleLabel: Int, logoutButton: View) {
        val sheet = BottomSheetDialog(activity)
        sheet.setContentView(R.layout.sheet_profile)
        sheet.findViewById<TextView>(R.id.tvProfileEmail)?.text = email ?: ""
        sheet.findViewById<TextView>(R.id.tvProfileRole)?.setText(roleLabel)
        sheet.findViewById<View>(R.id.btnProfileLogout)?.setOnClickListener {
            sheet.dismiss()
            logoutButton.performClick()
        }
        sheet.show()
    }
}
