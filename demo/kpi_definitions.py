"""KPI categories and KPIs per role, as used by the practice.

Copied from the KPI seed so the demo database scores staff against the
same KPIs the real app uses. Generic role expectations - no personal data.
"""

KPI_DEFINITIONS = {
    'Dental Assistant': {   'Clinical Support': {   'kpis': [   'Prepare treatment rooms accurately before '
                                            'each patient',
                                            'Assist chairside efficiently during '
                                            'procedures',
                                            'Correctly pass instruments and anticipate '
                                            'dentist needs',
                                            'Handle dental materials (impressions, '
                                            'cements) correctly',
                                            'Take and develop X-rays (if qualified) per '
                                            'protocol',
                                            'Maintain accurate and complete patient '
                                            'records'],
                                'weight': 30},
        'General Operations': {   'kpis': [   'Arrive on time for scheduled shifts',
                                              'Complete assigned tasks within required '
                                              'time',
                                              'Maintain clean and organized workstations',
                                              'Restock treatment rooms at end of day',
                                              'Attend scheduled training and staff '
                                              'meetings'],
                                  'weight': 25},
        'Infection Control & Sterilization': {   'kpis': [   'Follow all infection control '
                                                             'protocols strictly',
                                                             'Sterilize instruments '
                                                             'correctly using autoclave',
                                                             'Wear appropriate PPE at all '
                                                             'times',
                                                             'Dispose of sharps and '
                                                             'biohazard waste correctly',
                                                             'Complete daily sterilization '
                                                             'log accurately'],
                                                 'weight': 25},
        'Inventory & Stock Management': {   'kpis': [   'Monitor and report low stock '
                                                        'items',
                                                        'Store materials properly '
                                                        '(temperature, expiry)'],
                                            'weight': 10},
        'Patient Care & Communication': {   'kpis': [   'Greet and prepare patients warmly',
                                                        'Provide clear post-treatment '
                                                        'instructions when needed'],
                                            'weight': 10}},
    'Dentist': {   'Clinical Excellence': {   'kpis': [   'Complete procedures without need for redo',
                                               'Follow all clinical protocols and SOPs',
                                               'Update patient treatment plans accurately',
                                               'Ensure all notes are detailed and timely',
                                               'Maintain sterile technique throughout',
                                               'Meet or exceed patient satisfaction '
                                               'feedback'],
                                   'weight': 35},
        'Financial Performance': {   'kpis': [   'Generate target production value per day',
                                                 'Minimize no-shows through patient '
                                                 'engagement',
                                                 'Upsell appropriate treatments '
                                                 '(ethically)'],
                                     'weight': 30},
        'Patient Flow & Efficiency': {   'kpis': [   'Stay on schedule - avoid patient '
                                                     'delays',
                                                     'Complete all charting before leaving '
                                                     'for the day'],
                                         'weight': 15},
        'Professionalism': {   'kpis': [   'Maintain a respectful, collaborative attitude '
                                           'with staff',
                                           'Be available for emergencies within agreed '
                                           'hours'],
                               'weight': 10},
        'Systems & Compliance': {   'kpis': [   'Log into Dentally and update records '
                                                'daily',
                                                'Complete monthly compliance checklists'],
                                    'weight': 10}},
    'Receptionist': {   'Financial Administration': {   'kpis': [   'Collect payments at point of service '
                                                    '(no outstanding balances >48hrs)',
                                                    'Reconcile daily cash/card '
                                                    'transactions accurately',
                                                    'Follow up on outstanding '
                                                    'invoices/medical aid claims',
                                                    'Correctly process receipts and issue '
                                                    'to patients'],
                                        'weight': 30},
        'Operational Efficiency': {   'kpis': [   'Maintain accurate appointment bookings '
                                                  '(minimize double bookings)',
                                                  'Confirm appointments 24 hours in '
                                                  'advance',
                                                  'Process patient registration forms '
                                                  'completely',
                                                  'Keep waiting area tidy and stocked with '
                                                  'materials',
                                                  'Update patient records and contact '
                                                  'information'],
                                      'weight': 30},
        'Patient Communication': {   'kpis': [   'Answer all calls within 3 rings',
                                                 'Greet all patients warmly on arrival',
                                                 'Respond to queries or complaints '
                                                 'professionally',
                                                 'Send reminders via WhatsApp/SMS as '
                                                 'scheduled',
                                                 'Communicate delays to waiting patients '
                                                 'proactively'],
                                     'weight': 25},
        'Reporting & Administration': {   'kpis': [   'Submit daily reports to Practice '
                                                      'Manager on time',
                                                      'File documents (consent forms, '
                                                      'records) correctly',
                                                      'Log all incidents or unusual '
                                                      'occurrences'],
                                          'weight': 15}},
    'Cleaner': {   'Daily Hygiene Standards': {   'kpis': [   'Clean all treatment rooms between '
                                                   'patients',
                                                   'Sanitize all common areas (reception, '
                                                   'waiting, bathrooms)',
                                                   'Empty all bins and replace liners '
                                                   'daily',
                                                   'Mop and disinfect floors daily',
                                                   'Clean glass surfaces and mirrors'],
                                       'weight': 30},
        'Deep Cleaning & Maintenance': {   'kpis': [   'Complete weekly deep cleaning '
                                                       'checklist',
                                                       'Dust and clean air vents monthly',
                                                       'Polish floors as scheduled',
                                                       'Clean windows inside and out '
                                                       '(monthly)',
                                                       'Report maintenance issues '
                                                       'promptly'],
                                           'weight': 25},
        'Infection Control Compliance': {   'kpis': [   'Wear gloves and protective gear '
                                                        'while cleaning',
                                                        'Use correct disinfectants for '
                                                        'clinical areas',
                                                        'Dispose of clinical waste per '
                                                        'protocol',
                                                        'Clean and disinfect spittoons and '
                                                        'suction traps',
                                                        'Report any spills or hazards '
                                                        'immediately'],
                                            'weight': 30},
        'Professional Conduct': {   'kpis': [   'Arrive on time and complete tasks before '
                                                'practice opens',
                                                'Maintain stock of cleaning supplies',
                                                'Follow cleaning schedule without '
                                                'reminders',
                                                'Handle cleaning chemicals safely',
                                                'Maintain courteous interaction with staff '
                                                'and patients'],
                                    'weight': 15}},
}
