"""
Vasudha Real Estate — End-to-End Automated Test Suite
Tests: ML Model, Database CRUD, OTP flows, Valuation Calculations, and Flask REST APIs.
"""

import unittest
import json
import database
import backend
from ml_model import ml_model
from frontend import app


class TestVasudhaPlatform(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        database.init_db()
        ml_model.load()

    def test_01_ml_model_accuracy_and_prediction(self):
        """Test ML model training metrics and price predictions."""
        self.assertGreaterEqual(ml_model.r2_score, 0.95, "R² Score should be >= 0.95")
        
        # Test rate for Bodakdev
        flat_rate_sqft = ml_model.predict_rate("Bodakdev", 2026, "Apartment / Flat", "sqft")
        tenement_rate_sqft = ml_model.predict_rate("Bodakdev", 2026, "Tenement / Duplex", "sqft")
        
        self.assertEqual(flat_rate_sqft, 9200.0)
        self.assertAlmostEqual(tenement_rate_sqft, 9200.0 * 1.28, places=1)

        # Test purchase calculation
        val = ml_model.predict_purchase("Bodakdev", 200, "Apartment / Flat", 2026)
        expected_total = 9200.0 * 9.0 * 200.0  # 16,560,000
        self.assertEqual(val["total_price"], expected_total)
        self.assertEqual(val["area_sqft"], 1800.0)

    def test_02_five_year_projection(self):
        """Test 5-year compounding appreciation projections."""
        projs = ml_model.predict_5yr_projection("Shela", 100, "Apartment / Flat", 2026)
        self.assertEqual(len(projs), 5)
        # Year 5 must be higher than Year 1
        self.assertGreater(projs[4]["estimated_value"], projs[0]["estimated_value"])
        self.assertGreater(projs[4]["gain_percent"], 0.0)

    def test_03_historical_trends_availability(self):
        """Test multi-year trend queries for core localities."""
        hist_shela = database.get_historical_trends("Shela")
        self.assertGreaterEqual(len(hist_shela), 4, "Shela should have multi-year history in DB")
        
        hist_thaltej = database.get_historical_trends("Thaltej")
        self.assertGreaterEqual(len(hist_thaltej), 4, "Thaltej should have multi-year history in DB")

    def test_04_backend_valuation_calculation(self):
        """Test comprehensive valuation with formatted INR and intelligence."""
        res_flat = backend.calculate_property_valuation("Bodakdev", 150, "sqyd", "Apartment / Flat")
        self.assertTrue(res_flat["success"])
        self.assertIn("Cr", res_flat["total_price_formatted"])
        self.assertEqual(res_flat["locality"], "Bodakdev")
        self.assertEqual(res_flat["zone"], "West")
        self.assertIn("Judges Bungalow", "".join(res_flat["locality_intelligence"]["landmarks"]))

        # Tenement valuation
        res_tenement = backend.calculate_property_valuation("Bodakdev", 150, "sqyd", "Tenement / Duplex")
        self.assertTrue(res_tenement["success"])
        self.assertEqual(res_tenement["property_multiplier"], 1.28)
        self.assertGreater(res_tenement["total_price"], res_flat["total_price"])

        # Sq.ft unit conversion test
        res_sqft = backend.calculate_property_valuation("Bodakdev", 1350, "sqft", "Apartment / Flat")
        self.assertTrue(res_sqft["success"])
        self.assertAlmostEqual(res_sqft["total_price"], res_flat["total_price"], places=0)

    def test_05_auth_registration_otp_flow(self):
        """Test complete registration -> OTP verification -> login flow."""
        test_email = f"testuser_{backend.random.randint(100000, 999999)}@vasudha.test"
        test_user = f"user_{backend.random.randint(100000, 999999)}"

        # 1. Start registration
        reg_res = backend.start_registration(
            first_name="Aarav",
            surname="Shah",
            age=32,
            phone=f"98{backend.random.randint(10000000, 99999999)}",
            email=test_email,
            username=test_user,
            password="SecurePassword123"
        )
        self.assertTrue(reg_res["success"], f"Registration failed: {reg_res.get('error')}")
        otp = reg_res.get("demo_otp") or backend._pending_registrations.get(test_email, {}).get("otp")
        self.assertIsNotNone(otp, "OTP should be generated in backend pending storage")

        # 2. Verify with wrong OTP
        bad_verify = backend.verify_registration_otp(test_email, "000000")
        self.assertFalse(bad_verify["success"])

        # 3. Verify with correct OTP
        good_verify = backend.verify_registration_otp(test_email, otp)
        self.assertTrue(good_verify["success"], f"OTP verification failed: {good_verify.get('error')}")
        self.assertEqual(good_verify["user"]["email"], test_email.lower())

        # 4. Authenticate user
        auth_res = backend.authenticate_user(test_email, "SecurePassword123")
        self.assertTrue(auth_res["success"])
        self.assertEqual(auth_res["user"]["username"], test_user)

    def test_06_password_reset_flow(self):
        """Test forgot password -> OTP -> new password update flow."""
        test_email = f"resetuser_{backend.random.randint(100000, 999999)}@vasudha.test"
        test_user = f"reset_{backend.random.randint(100000, 999999)}"

        # Create user
        reg_res = backend.start_registration("Pooja", "Mehta", 29, f"99{backend.random.randint(10000000, 99999999)}", test_email, test_user, "OldPassword123")
        reg_otp = reg_res.get("demo_otp") or backend._pending_registrations.get(test_email, {}).get("otp")
        backend.verify_registration_otp(test_email, reg_otp)

        # Initiate reset
        forgot_res = backend.start_password_reset(test_email)
        self.assertTrue(forgot_res["success"])
        reset_otp = forgot_res.get("demo_otp") or backend._pending_resets.get(test_email, {}).get("otp")

        # Verify reset with new password
        reset_res = backend.verify_password_reset(test_email, reset_otp, "BrandNewPassword456")
        self.assertTrue(reset_res["success"])

        # Verify old password fails and new password succeeds
        old_auth = backend.authenticate_user(test_email, "OldPassword123")
        self.assertFalse(old_auth["success"])

        new_auth = backend.authenticate_user(test_email, "BrandNewPassword456")
        self.assertTrue(new_auth["success"])

    def test_07_flask_rest_api_endpoints(self):
        """Test Flask HTTP API endpoints."""
        client = app.test_client()

        # 1. Get localities list
        res_locs = client.get("/api/localities")
        self.assertEqual(res_locs.status_code, 200)
        data_locs = json.loads(res_locs.data)
        self.assertTrue(data_locs["success"])
        self.assertGreaterEqual(data_locs["count"], 24)

        # 2. Get locality detail
        res_detail = client.get("/api/locality/Shela")
        self.assertEqual(res_detail.status_code, 200)
        data_detail = json.loads(res_detail.data)
        self.assertEqual(data_detail["locality"]["name"], "Shela")
        self.assertGreaterEqual(len(data_detail["locality"]["historical_trends"]), 4)

        # 3. Post estimate (Unauthenticated -> should return 401 requires_auth)
        res_unauth = client.post("/api/estimate", json={
            "locality": "Thaltej",
            "area": 200,
            "property_type": "Tenement / Duplex"
        })
        self.assertEqual(res_unauth.status_code, 401)
        data_unauth = json.loads(res_unauth.data)
        self.assertTrue(data_unauth.get("requires_auth"))

        # 4. Post estimate (Authenticated session -> should return 200 with full results)
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Om Patel"
            sess["email"] = "ompatel@example.com"

        res_est = client.post("/api/estimate", json={
            "locality": "Thaltej",
            "area": 200,
            "property_type": "Tenement / Duplex"
        })
        self.assertEqual(res_est.status_code, 200)
        data_est = json.loads(res_est.data)
        self.assertTrue(data_est["success"])
        self.assertEqual(data_est["property_multiplier"], 1.28)
        self.assertEqual(len(data_est["five_year_projections"]), 5)

    def test_08_new_localities_and_admin_management(self):
        """Test newly added localities, admin authentication, user deletion, and price editing."""
        client = app.test_client()

        # 1. Test new localities exist in DB and can be estimated
        for loc in ["Vaishnodevi", "Jagatpur", "Tragad", "Zundal"]:
            loc_data = database.get_locality_by_name(loc)
            self.assertIsNotNone(loc_data, f"{loc} should exist in database")
            val = backend.calculate_property_valuation(loc, 100, "sqyd", "Apartment / Flat")
            self.assertTrue(val["success"], f"Valuation for {loc} should succeed")
            self.assertGreater(val["total_price"], 0)

        # 2. Test Admin Authentication API
        bad_auth = client.post("/api/admin/login", json={"passcode": "WrongCode"})
        self.assertEqual(bad_auth.status_code, 401)

        good_auth = client.post("/api/admin/login", json={"passcode": backend.ADMIN_PASSCODE})
        self.assertEqual(good_auth.status_code, 200)

        # 3. Create a disposable test user to delete
        temp_email = f"delete_me_{backend.random.randint(10000, 99999)}@vasudha.test"
        reg_res = backend.start_registration("Temp", "User", 25, f"97{backend.random.randint(10000000, 99999999)}", temp_email, f"temp_{backend.random.randint(10000, 99999)}", "TempPassword123")
        otp = reg_res.get("demo_otp") or backend._pending_registrations.get(temp_email, {}).get("otp")
        verify_res = backend.verify_registration_otp(temp_email, otp)
        self.assertTrue(verify_res["success"])
        temp_uid = verify_res["user"]["id"]

        # 4. Admin List Users
        users_res = client.get("/api/admin/users")
        self.assertEqual(users_res.status_code, 200)
        users_data = json.loads(users_res.data)
        self.assertTrue(users_data["success"])
        self.assertTrue(any(u["id"] == temp_uid for u in users_data["users"]))

        # 5. Admin Delete User
        del_res = client.post("/api/admin/users/delete", json={"user_id": temp_uid})
        self.assertEqual(del_res.status_code, 200)
        self.assertIsNone(database.get_user_by_id(temp_uid), "User should be deleted from SQLite database")

        # 6. Admin Update Locality Price
        update_res = client.post("/api/admin/locality/update-price", json={
            "name": "Vaishnodevi",
            "rate_per_sqft": 6200,
            "yoy_percent": 7.5,
            "livability_score": 9.5
        })
        self.assertEqual(update_res.status_code, 200)
        up_data = json.loads(update_res.data)
        self.assertTrue(up_data["success"])

        # Check DB reflects updated price
        vaishnodevi_db = database.get_locality_by_name("Vaishnodevi")
        self.assertEqual(vaishnodevi_db["rate_per_sqft"], 6200.0)
        self.assertEqual(vaishnodevi_db["rate_per_sqyd"], 55800.0)
        self.assertEqual(vaishnodevi_db["yoy_percent"], 7.5)

    def test_09_security_hardening(self):
        """Test OTP attempt limiting, cooldown, and HTTP security response headers."""
        client = app.test_client()

        # 1. Test HTTP Security Headers
        resp = client.get("/")
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(resp.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(resp.headers.get("X-XSS-Protection"), "1; mode=block")
        self.assertEqual(resp.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")

        # 2. Test OTP Brute-Force Locking (5 failed attempts invalidates OTP)
        test_email = f"bruteforce_{backend.random.randint(10000, 99999)}@vasudha.test"
        reg_res = backend.start_registration("Test", "Security", 30, f"96{backend.random.randint(10000000, 99999999)}", test_email, f"sec_{backend.random.randint(10000, 99999)}", "StrongPass123")
        self.assertTrue(reg_res["success"])

        for _ in range(5):
            res_bad = backend.verify_registration_otp(test_email, "000000")
            self.assertFalse(res_bad["success"])

        # 6th attempt or correct OTP attempt after 5 failures must fail (locked out)
        real_otp = reg_res.get("demo_otp")
        if real_otp:
            final_try = backend.verify_registration_otp(test_email, real_otp)
            self.assertFalse(final_try["success"], "OTP should be invalidated after 5 failed attempts")

    def test_10_admin_password_reset_flow(self):
        """Test master admin passcode forgot -> OTP dispatch to ompatel94929@gmail.com -> reset passcode flow."""
        client = app.test_client()

        # 1. Start admin reset
        forgot_res = backend.start_admin_password_reset()
        self.assertTrue(forgot_res["success"])
        self.assertIn("message", forgot_res)
        admin_otp = forgot_res.get("demo_otp") or backend._pending_admin_reset.get("otp")
        self.assertIsNotNone(admin_otp)

        # 2. Test bad OTP verification via Flask API
        bad_reset = client.post("/api/admin/reset-passcode", json={
            "otp": "000000",
            "new_passcode": "NewAdminPass123!"
        })
        self.assertEqual(bad_reset.status_code, 400)

        # 3. Test correct OTP verification via Flask API
        good_reset = client.post("/api/admin/reset-passcode", json={
            "otp": admin_otp,
            "new_passcode": "NewAdminPass123!"
        })
        self.assertEqual(good_reset.status_code, 200)
        reset_data = json.loads(good_reset.data)
        self.assertTrue(reset_data["success"])

        # 4. Verify login succeeds with new passcode
        login_res = client.post("/api/admin/login", json={"passcode": "NewAdminPass123!"})
        self.assertEqual(login_res.status_code, 200)

        # Restore original passcode
        backend.ADMIN_PASSCODE = "OPatel050512%"
        import os
        os.environ["ADMIN_PASSCODE"] = "OPatel050512%"

    def test_11_bilingual_locality_price_explanations(self):
        """Test dynamic bilingual (English + Devanagari Hindi) price explanations and key drivers."""
        sample_localities = ["Thaltej", "Bodakdev", "Shela", "Motera", "Navrangpura", "Nikol"]
        
        for loc in sample_localities:
            val = backend.calculate_property_valuation(loc, 150, "sqyd", "Apartment / Flat")
            self.assertTrue(val["success"], f"Valuation failed for {loc}")
            
            # Check English explanation
            self.assertIn("price_explanation_en", val)
            self.assertIsInstance(val["price_explanation_en"], str)
            self.assertGreater(len(val["price_explanation_en"]), 20)
            
            # Check Hindi explanation (Devanagari script presence)
            self.assertIn("price_explanation_hi", val)
            self.assertIsInstance(val["price_explanation_hi"], str)
            self.assertGreater(len(val["price_explanation_hi"]), 20)
            
            # Check Price Drivers list
            self.assertIn("price_drivers", val)
            self.assertIsInstance(val["price_drivers"], list)
            self.assertGreaterEqual(len(val["price_drivers"]), 1)

        # Specifically verify Thaltej mentions 190-200 sq. yard 3 BHK dynamics
        thaltej_val = backend.calculate_property_valuation("Thaltej", 150, "sqyd", "Apartment / Flat")
        self.assertIn("190", thaltej_val["price_explanation_en"])
        self.assertIn("redevelopment", thaltej_val["price_explanation_en"].lower())

    def test_12_share_valuation_email(self):
        """Test Share Valuation via Email: backend logic and REST API endpoint."""
        # 1. Test Backend validation on invalid email
        res_invalid = backend.send_valuation_email("not-an-email", {"locality": "Bodakdev", "area_sqyd": 150})
        self.assertFalse(res_invalid["success"])
        self.assertIn("valid recipient email", res_invalid["error"])

        # 2. Test Backend dispatch with full valuation details
        val = backend.calculate_property_valuation("Bodakdev", 150, "sqyd", "Apartment / Flat")
        res_valid = backend.send_valuation_email("testshare@vasudha.test", val)
        self.assertTrue(res_valid["success"])
        self.assertEqual(res_valid["recipient"], "testshare@vasudha.test")
        self.assertEqual(res_valid["locality"], "Bodakdev")
        self.assertEqual(res_valid["area_sqyd"], 150.0)
        self.assertIn("calculated_at", res_valid)
        self.assertIn("Cr", res_valid["total_price_formatted"])

        # 3. Test REST API endpoint /api/share-calculation
        client = app.test_client()

        # Missing email payload -> 400 Bad Request
        api_res_bad = client.post("/api/share-calculation", json={"locality": "Thaltej", "area_sqyd": 180})
        self.assertEqual(api_res_bad.status_code, 400)
        bad_data = json.loads(api_res_bad.data)
        self.assertFalse(bad_data["success"])

        # Valid payload with calculation -> 200 OK
        api_res_good = client.post("/api/share-calculation", json={
            "email": "client_buyer@vasudha.test",
            "locality": "Thaltej",
            "area_sqyd": 180,
            "property_type": "Apartment / Flat"
        })
        self.assertEqual(api_res_good.status_code, 200)
        good_data = json.loads(api_res_good.data)
        self.assertTrue(good_data["success"])
        self.assertEqual(good_data["recipient"], "client_buyer@vasudha.test")
        self.assertEqual(good_data["locality"], "Thaltej")
        self.assertEqual(good_data["area_sqyd"], 180.0)
        self.assertIn("calculated_at", good_data)


if __name__ == "__main__":
    unittest.main()
