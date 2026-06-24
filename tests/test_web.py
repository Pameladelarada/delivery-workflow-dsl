import io
import re
import unittest

from web.app import app


class WebIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_editor_starts_empty_and_html_is_not_cached(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        editor = re.search(r'<textarea id="source"[^>]*>(.*?)</textarea>', html, re.DOTALL)

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(editor)
        self.assertEqual(editor.group(1), "")
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_uploaded_rules_generate_a_specific_dsl_draft(self):
        rules = (
            "cliente: Juan Perez\n"
            "producto: Pizza Familiar\n"
            "total: 95\n"
            "pago: YAPE\n"
            "direccion: Av. Los Alamos 123\n"
            "stock: 2\n"
        )
        response = self.client.post(
            "/upload-rules",
            data={"rules": (io.BytesIO(rules.encode("utf-8")), "reglas.txt")},
            content_type="multipart/form-data",
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertIn('cliente: "Juan Perez"', payload["dsl_draft"])
        self.assertIn("total: 95", payload["dsl_draft"])
        self.assertNotIn('cliente: "Carlos"', payload["dsl_draft"])

    def test_tabular_label_value_rules_preserve_all_invoice_fields(self):
        rules = """PEDIDO
PED-2026001
EMPRESA
Delivery Express SAC
RUC
20601234567
FECHA
22/06/2026 19:35
CLIENTE
Juan Perez
DIRECCION
Av. Los Alamos 123, Lima
PRODUCTO
Pizza Familiar x1, Gaseosa 1.5L x1
SUBTOTAL
45.0
COSTO ENVIO
5.0
IGV
8.1
TOTAL
58.1
METODO PAGO
Yape
ESTADO
ENTREGADO
"""
        response = self.client.post(
            "/upload-rules",
            data={"rules": (io.BytesIO(rules.encode("utf-8")), "boleta.txt")},
            content_type="multipart/form-data",
        )
        draft = response.get_json()["dsl_draft"]

        self.assertIn('pedido_id: "PED-2026001"', draft)
        self.assertIn('empresa: "Delivery Express SAC"', draft)
        self.assertIn('cliente: "Juan Perez"', draft)
        self.assertIn('producto: "Pizza Familiar x1, Gaseosa 1.5L x1"', draft)
        self.assertIn("total: 58.1", draft)
        self.assertIn("pago: YAPE", draft)
        self.assertIn("estado: ENTREGADO", draft)
        self.assertIn("stock: 2", draft)


if __name__ == "__main__":
    unittest.main(verbosity=2)
