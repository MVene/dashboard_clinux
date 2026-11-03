"""Chequeos de la versión ejecutiva sin conexión externa."""
import unittest
from scripts.build_grafana_json import dashboard, ARS
from scripts.etl import TABLES_DDL, ETL_RULES_VERSION


class DashboardV4(unittest.TestCase):
    def test_tiene_solo_paneles_solicitados(self):
        self.assertEqual(len(dashboard['panels']), 10)
        titles = {x['title'] for x in dashboard['panels']}
        self.assertIn('Ventas mayoristas · período', titles)
        self.assertIn('Ventas minoristas · período', titles)
        self.assertIn('Detalle de clientes mayoristas', titles)
        self.assertNotIn('Stock por debajo del umbral configurable', titles)

    def test_ganancias_diferenciadas(self):
        profits = [x for x in dashboard['panels'] if x['title'].startswith('Ganancia registrada')]
        self.assertEqual(len(profits), 2)
        self.assertTrue(all('ganancia_registrada' in x['targets'][0]['rawSql'] for x in profits))
        self.assertTrue(all('clinux_clientes_diarios' in x['targets'][0]['rawSql'] for x in profits))

    def test_moneda_y_variable(self):
        self.assertEqual(dashboard['templating']['list'][0]['name'], 'DS_CLINUX')
        cash_panels = [p for p in dashboard['panels'] if p['type'] in ('stat','timeseries') and p['fieldConfig']['defaults']['unit'] == ARS]
        self.assertGreaterEqual(len(cash_panels), 5)
        self.assertTrue(all(x['fieldConfig']['defaults']['decimals'] == 0 for x in cash_panels))
        self.assertTrue(all(p['datasource']['uid'] == '${DS_CLINUX}' for p in dashboard['panels']))

    def test_migracion_base_y_reprocesamiento(self):
        self.assertTrue(any('ADD COLUMN IF NOT EXISTS ganancia_registrada' in x for x in TABLES_DDL))
        self.assertIn('v4-', ETL_RULES_VERSION)

    def test_ingresos_y_ganancias_filtrados_por_periodo(self):
        for p in dashboard['panels']:
            if p['title'].startswith(('Ventas mayoristas', 'Ventas minoristas', 'Ganancia registrada')):
                self.assertIn('$__timeFilter', p['targets'][0]['rawSql'])


if __name__ == '__main__':
    unittest.main()
