"""Comprobaciones de contenido y formato sin red ni escritura del informe."""
import ast
import re
import unittest
from pathlib import Path

from docx import Document
from documento_academico import AUTHORS, ROOT, observed_recovery, select_evidence


class AcademicReport(unittest.TestCase):
    def test_recovery_uses_timestamps_not_sum_of_failed_queries(self):
        rows = [
            {'vm': 'vm1', 'step': 'detener dn', 'returncode': 0, 'utc': '2026-11-06T02:00:00+00:00'},
            {'vm': 'vm4', 'step': 'sonda repaired', 'returncode': 1, 'seconds': 2, 'utc': '2026-11-06T02:00:20+00:00'},
            {'vm': 'vm4', 'step': 'sonda repaired', 'returncode': 0, 'seconds': 2, 'utc': '2026-11-06T02:00:45+00:00'},
        ]
        self.assertEqual(observed_recovery(rows)[2], 45)

    def test_evidence_has_matching_fingerprint_and_actual_interval(self):
        bench, regression, records, rows = select_evidence()
        self.assertEqual(bench['source_sha256'], regression['source_sha256'])
        self.assertEqual(regression['tests'], 19)
        self.assertEqual(len(rows), 16)
        self.assertAlmostEqual(observed_recovery(records)[2], 41.394787, places=5)

    def test_report_is_self_contained_and_preserves_evaluable_content(self):
        doc = Document(ROOT / 'DFSha_FaseII_Informe_Grupal.docx')
        paragraphs = [p.text for p in doc.paragraphs]
        all_text = '\n'.join(paragraphs + [c.text for t in doc.tables for row in t.rows for c in row.cells])
        self.assertIsNone(re.search(r'\.(?:md|py|proto|json)\b', all_text, re.I))
        self.assertEqual(len(doc.inline_shapes), 9)
        self.assertEqual(len([p for p in paragraphs if re.match(r'^\[\d+\]', p)]), 11)
        for number in range(1, 12):
            self.assertTrue(any(p.startswith(str(number) + '. ') for p in paragraphs))
        for author in AUTHORS:
            self.assertIn(author, paragraphs)
        self.assertIn('41.4 segundos', all_text)
        self.assertNotIn('7 s de reparación', all_text)
        self.assertIn('BAD_RECEIPT', all_text)
        self.assertIn('200 OK', all_text)
        self.assertIn('409 Conflict', all_text)

    def test_cover_has_page_number_margins_and_double_spacing(self):
        doc = Document(ROOT / 'DFSha_FaseII_Informe_Grupal.docx')
        for margin in ('top_margin', 'bottom_margin', 'left_margin', 'right_margin'):
            self.assertAlmostEqual(getattr(doc.sections[0], margin).cm, 2.54, places=2)
        header = doc.sections[0].header._element
        # Word convierte fldSimple en un campo complejo al guardar manualmente.
        simple_fields = header.xpath('.//w:fldSimple/@w:instr')
        complex_fields = header.xpath('.//w:instrText/text()')
        self.assertTrue(any(re.search(r'\bPAGE\b', instruction)
                            for instruction in simple_fields + complex_fields))
        for paragraph in doc.paragraphs[:9]:
            self.assertEqual(paragraph.paragraph_format.line_spacing, 2)
        self.assertTrue(all(run.bold for run in doc.paragraphs[0].runs))

    def test_restore_attempts_all_services_after_one_failure(self):
        source = ROOT / 'dfsha/scripts/verify_aws.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        restore = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'restore_all')
        namespace = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[restore], type_ignores=[])), str(source), 'exec'), namespace)
        stopped = [('vm1', 'etcd'), ('vm2', 'etcd'), ('vm3', 'dn')]
        attempts = []
        def restart(vm, service):
            attempts.append((vm, service))
            if vm == 'vm3':
                raise RuntimeError('SSH indisponible')
            stopped.remove((vm, service))
        errors = namespace['restore_all'](stopped, restart)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len(errors), 1)
        self.assertEqual(stopped, [('vm3', 'dn')])


if __name__ == '__main__':
    unittest.main(verbosity=2)
