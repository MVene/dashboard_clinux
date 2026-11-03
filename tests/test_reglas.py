"""Pruebas simples de clasificación. Ejecutar: python -m unittest discover -s tests -v"""
import unittest
import pandas as pd
from scripts.metrics import mark_wholesale

class ReglasClinux(unittest.TestCase):
    def test_cliente_identificado_prioriza_factura(self):
        data = pd.DataFrame({'tipo':['FC','FX','FC','FX','NC'],
            'cliente':['CF','CF','CLIENTE-01','CLIENTE-02','CLIENTE-01']})
        actual = mark_wholesale(data)['mayorista'].tolist()
        self.assertEqual(actual, [False, False, True, True, True])
    def test_falta_cliente_es_minorista(self):
        data=pd.DataFrame({'tipo':['FX','FC'],'cliente':[None, '']})
        self.assertEqual(mark_wholesale(data)['mayorista'].tolist(), [False, False])

if __name__=='__main__':unittest.main()
