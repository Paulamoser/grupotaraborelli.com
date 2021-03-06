# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime,date,timedelta
from dateutil import relativedelta
import base64
import logging
_logger = logging.getLogger(__name__)

try:
    from base64 import encodebytes
except ImportError:  # 3+
    from base64 import encodestring as encodebytes

class AccountExportSircarNeuquen(models.Model):
    _name = 'account.export.sircar.neuquen'
    _description = 'account.export.sircar.neuquen'

    name = fields.Char('Nombre')
    date_from = fields.Date('Fecha desde')
    date_to = fields.Date('Fecha hasta')
    export_sircar_neuquen_data_ret = fields.Text('Contenidos archivo SIRCAR Neuquen Ret', default='')
    export_sircar_neuquen_data_per = fields.Text('Contenidos archivo SIRCAR Neuquen Per', default='')
    tax_withholding = fields.Many2one('account.tax','Imp. de ret utilizado', domain=[('tax_sircar_neuquen_ret', '=', True)], required=True)
    
    #Retenciones
    @api.depends('export_sircar_neuquen_data_ret')
    def _compute_files_ret(self):
        self.ensure_one()
        self.export_sircar_neuquen_filename_ret = _('Sircar_neuquen_ret_%s_%s.txt') % (str(self.date_from),str(self.date_to))
        self.export_sircar_neuquen_file_ret = encodebytes(self.export_sircar_neuquen_data_ret.encode('ISO-8859-1'))
    export_sircar_neuquen_file_ret = fields.Binary('TXT SIRCAR Neuquen Ret',compute=_compute_files_ret)
    export_sircar_neuquen_filename_ret = fields.Char('TXT SIRCAR Neuquen Ret',compute=_compute_files_ret) 
    
    #Percepciones
    @api.depends('export_sircar_neuquen_data_per')
    def _compute_files_per(self):
        self.ensure_one()
        self.export_sircar_neuquen_filename_per = _('Sircar_neuquen_per_%s_%s.txt') % (str(self.date_from),str(self.date_to))
        self.export_sircar_neuquen_file_per = encodebytes(self.export_sircar_neuquen_data_per.encode('ISO-8859-1'))
    export_sircar_neuquen_file_per = fields.Binary('TXT SIRCAR Neuquen Per',compute=_compute_files_per)
    export_sircar_neuquen_filename_per = fields.Char('TXT SIRCAR Neuquen Per',compute=_compute_files_per)


    def compute_sircar_neuquen_data(self):
        self.ensure_one()
        windows_line_ending = '\r' + '\n'

        # Retenciones
        payments = self.env['account.payment'].search([('payment_type','=','outbound'),('state','not in',['cancel','draft']),('date','<=',self.date_to),('date','>=',self.date_from)])
        string = ''
        num_renglon = 1
        for payment in payments:
            if not payment.withholding_number:
                continue
            if payment.tax_withholding_id.id != self.tax_withholding.id:
                continue
            # TXT segun formato de https://www.comarb.gob.ar/descargar/sircar/Anexo_Registros.pdf
            if len(payment.partner_id) < 1:
                raise ValidationError('El pago {0} no tiene asignado un cliente'.format(payment.name))
            _alicuota_ret = payment.partner_id.alicuot_ret_sircar_neuquen_ids.filtered(lambda l: l.padron_activo == True)[0].a_ret
            
            # 1 N??mero de Rengl??n (??nico por archivo. Long: 5. Formato 99999
            string = string + str(num_renglon).zfill(5) + ','
            # 2 campo Origen del Comprobante. Long: 1. 1 Comprobante Generado por Software propio del Agente / 2 Comprobante Generado por Sistema SIRCAR
            string = string + '1' + ','
            # 3 campo Tipo de Comprobante. Long: 1. 1 Comprobante de Retenci??n / 2 Comprobante de Anulaci??n de Retenci??n
            string = string + '1' + ','
            # 4 campo N??mero de Comprobante. Long: 12.
            string = string + payment.withholding_number.zfill(12) + ','
            # 5 campo CUIT Contribuyente involucrado en la transacci??n Comercial. Long: . Formato 99-99999999-9
            string = string + payment.partner_id.vat + ','
            # 6 campo Fecha de Retenci??n . Long: 10. Formato dd/mm/aaaa.
            string = string + str(payment.date)[8:10] + '/' + str(payment.date)[5:7] + '/' + str(payment.date)[:4] + ','
            # 7 campo Monto Sujeto a Retenci??n (num??rico sin separador de miles)
            string = string + ("%.2f"%(payment.withholding_base_amount)) + ','
            # 8 campo Al??cuota (porcentaje sin separador de miles) . Ej: 42.03
            string = string + "%.2f"%_alicuota_ret + ','
            # 9 campo Monto Retenido (num??rico sin separador de miles, se obtiene de multiplicar el campo 7 por el campo 8 y dividirlo por 100)
            string = string + "%.2f"%((payment.withholding_base_amount * _alicuota_ret)/100) + ','
            #PUNTO 10 Y 11 SEGUN https://www.ca.gov.ar/descargar/sircar/sircar_regimenes_jur_version_36_25-03-2022.xlsx
            # 10 Tipo de R??gimen de Percepci??n (c??digo correspondiente seg??n tabla definida por la jurisdicci??n)
            string = string + '030' + ','
            # 11 Jurisdicci??n: c??digo en Convenio Multilateral de la jurisdicci??n a la cual est?? presentando la DDJJ
            string = string + '915'
            # CRLF
            string = string + windows_line_ending
            num_renglon += 1
            
        self.export_sircar_neuquen_data_ret = string

        # Percepciones
        invoices = self.env['account.move'].search([('move_type','in',['out_invoice','out_refund']),('state','=','posted'),('invoice_date','<=',self.date_to),('invoice_date','>=',self.date_from)],order='invoice_date asc')
        string = ''
        num_renglon = 0
        for invoice in invoices:
            for group in invoice.amount_by_group:
                if group[0] == 'Perc IIBB Neuqu??n':
                    _alicuota = invoice.partner_id.alicuot_per_sircar_neuquen_ids.filtered(lambda l: l.padron_activo == True)[0].a_per
                    
                    # TXT segun formato https://www.comarb.gob.ar/descargar/sircar/Anexo_Registros.pdf
                    # 1 N??mero de Rengl??n (??nico por archivo. Long: 5. Formato 99999
                    string = string + str(num_renglon).zfill(5) + ','
                    # 2 Tipo de Comprobante. Long: 3. Formato : 1 Factura
                                                                # 2 Nota de D??bito
                                                                # 3 Recibo
                                                                # 4 Nota de Venta al Contado
                                                                # 5 Factura Exportaci??n
                                                                # 6 Nota D??bito para operaciones c/exterior
                                                                # 7 Liquidaci??n
                                                                # 20 Otros Comprobantes de D??bito
                                                                # 102 Nota Cr??dito
                                                                # 106 Nota Cr??dito para operaciones c/exterior
                                                                # 120 Otros Comprobantes de Cr??dito
                    if invoice.l10n_latam_document_type_id.internal_type == 'invoice':
                        string = string + '001' + ','
                    elif invoice.l10n_latam_document_type_id.internal_type == 'credit_note':
                        string = string + '102' + ','
                    elif invoice.l10n_latam_document_type_id.internal_type == 'debit_note':
                        string = string + '002' + ','
                    # 3 Letra del Comprobante (A, B, C, E ?? M, seg??n tipo de Comprobante) Z si no existe identificaci??n del Comprobante. Long: 1.
                    string = string + invoice.l10n_latam_document_type_id.l10n_ar_letter + ','
                    # 4 N??mero de Comprobante (incluye el punto de venta) . Long: 12. Ej: 000023431222
                    string = string + str(invoice.name)[6:10] + str(invoice.name)[-8:] + ','
                    # 5 CUIT Contribuyente involucrado en la transacci??n Comercial . Long: 1. Ej: 30100100106
                    string = string + str(invoice.partner_id.vat) + ','
                    # 6 Fecha de Percepci??n. Long: 10. (en formato dd/mm/aaaa) ej: 03/12/2015
                    string = string + str(invoice.invoice_date)[8:10] + '/' + str(invoice.invoice_date)[5:7] + '/' + str(invoice.invoice_date)[:4] + ','
                    # 7 Monto Sujeto a Percepci??n (num??rico sin separador de miles). Ej: 999999999.99
                    string = string + "%.2f"%invoice.amount_untaxed + ','
                    # 8 Al??cuota (porcentaje sin separador de miles) . Ej: 42.03
                    string = string + "%.2f"%_alicuota + ','
                    # 9 Monto Percibido (num??rico sin separador de miles, se obtiene de multiplicar el campo 7 por el campo 8 y dividirlo por 100). Ej: 999999999.99
                    string = string + "%.2f"%((invoice.amount_untaxed * _alicuota)/100) + ','
                    #PUNTO 10 Y 11 SEGUN https://www.ca.gov.ar/descargar/sircar/sircar_regimenes_jur_version_36_25-03-2022.xlsx
                    # 10 Tipo de R??gimen de Percepci??n (c??digo correspondiente seg??n tabla definida por la jurisdicci??n)
                    string = string + '040' + ','
                    # 11 Jurisdicci??n: c??digo en Convenio Multilateral de la jurisdicci??n a la cual est?? presentando la DDJJ
                    string = string + '915'

                    string = string + windows_line_ending
                    num_renglon += 1
                    
        self.export_sircar_neuquen_data_per = string


