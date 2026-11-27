import unittest
import voice_diagnostics

class VoiceMetrics(unittest.TestCase):
    def test_records_only_transient_operational_metrics(self):
        voice_diagnostics.record({'client_id':'fixture-metrics','phase':'listening','input_level':.025,
            'counts':{'speech_started':2,'pcm_bytes':48000,'private_counter':7},
            'text':'private conversation','audio':'private audio','api_key':'private credential'})
        snapshot=next(row for row in voice_diagnostics.snapshots()['clients'] if row['client_id']=='fixture-metrics')
        self.assertNotIn('text',snapshot)
        self.assertNotIn('audio',snapshot)
        self.assertNotIn('api_key',snapshot)
        self.assertEqual(snapshot['counts'],{'speech_started':2,'pcm_bytes':48000})
        self.assertEqual(snapshot['input_level'],.025)

    def test_peak_remains_available_after_input_stops_and_is_bounded(self):
        voice_diagnostics.record({'client_id':'fixture-peak','phase':'stopped','input_level':0,'input_peak':.18})
        snapshot=next(row for row in voice_diagnostics.snapshots()['clients'] if row['client_id']=='fixture-peak')
        self.assertEqual(snapshot['input_level'],0)
        self.assertEqual(snapshot['input_peak'],.18)
        voice_diagnostics.record({'client_id':'fixture-peak','input_peak':float('nan')})
        snapshot=next(row for row in voice_diagnostics.snapshots()['clients'] if row['client_id']=='fixture-peak')
        self.assertNotIn('input_peak',snapshot)

if __name__=='__main__':unittest.main()
