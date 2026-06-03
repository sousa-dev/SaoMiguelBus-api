"""Tests for açores.net digest HTML parsing."""

from django.test import SimpleTestCase

from news.adapters.azores import parse_azores_digest

ALRA_FIXTURE = """
<h2 id="alra">ALRA</h2>
<h3 id="requerimentos">Requerimentos</h3>
<ul>
  <li><a href="http://base.alra.pt:82/4DACTION/w_pesquisa_registo/4/9280">Apuramento de responsabilidades por atos de captura ilegal e maus-tratos infligidos a tubarão</a>
    <ul>
      <li>Alteração do estado: NO PRAZO → RESPOSTA ATEMPADA</li>
      <li><a href="http://base.alra.pt:82/Doc_Req/XIIIreque636.pdf">requerimento</a>( data entrada: 30/04/2026)</li>
      <li>Requerente(s): António Lima BE</li>
    </ul>
  </li>
  <li><a href="http://base.alra.pt:82/4DACTION/w_pesquisa_registo/4/9291">Dois anos e meio depois e ainda não existe projeto do novo Centro de Saúde da Ribeira Grande</a>
    <ul>
      <li>Alteração do estado: NO PRAZO → RESPOSTA ATEMPADA</li>
      <li>Requerente(s): Carlos Silva PS, …</li>
    </ul>
  </li>
</ul>
<h3 id="informações">Informações</h3>
<ul>
  <li><a href="http://base.alra.pt:82/4DACTION/w_pesquisa_registo/8/23586">Nota de Imprensa do Grupo Parlamentar do CHEGA</a>
    <ul>
      <li><a href="http://base.alra.pt:82/Doc_Noticias/NI23586.pdf">pdf</a></li>
    </ul>
  </li>
</ul>
"""

JORAA_FIXTURE = """
<h2 id="joraa">JORAA</h2>
<ul>
  <li><a href="https://jo.azores.gov.pt/#/ato/78c608cb-05f7-43a2-9222-40b3ffcab0b1">Apoios financeiros destinados à manutenção da cultura da vinha da ilha do Pico - Oitavo pagamento.</a>
    <ul>
      <li>Despacho n.º 1218/2026 de 2 de junho de 2026</li>
      <li>Soma dos montantes: 328,640.81 €</li>
      <li>Secretaria Regional do Ambiente e Ação Climática</li>
    </ul>
  </li>
  <li><a href="https://jo.azores.gov.pt/#/ato/a6a5cef5-cbef-458e-9952-5b59f01e581c">1.º Aditamento ao Contrato-Programa de Desenvolvimento Desportivo.</a>
    <ul>
      <li>Aditamento n.º 42/2026 de 2 de junho de 2026</li>
      <li>Soma dos montantes: 248,857.00 €</li>
    </ul>
  </li>
</ul>
"""


class AzoresAdapterTestCase(SimpleTestCase):
    def test_alra_splits_requerimentos_and_informacoes(self):
        items = parse_azores_digest(ALRA_FIXTURE)
        self.assertEqual(len(items), 3)

        req_items = [i for i in items if i['section'] == 'Requerimentos']
        self.assertEqual(len(req_items), 2)
        self.assertIn('base.alra.pt', req_items[0]['link'])
        self.assertIn('tubarão', req_items[0]['title'])
        self.assertIn('Alteração do estado', req_items[0]['summary'])
        self.assertIn('António Lima BE', req_items[0]['summary'])

        info_items = [i for i in items if i['section'] == 'Informações']
        self.assertEqual(len(info_items), 1)
        self.assertIn('CHEGA', info_items[0]['title'])

    def test_joraa_splits_payment_items(self):
        items = parse_azores_digest(JORAA_FIXTURE)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['section'], '')
        self.assertIn('jo.azores.gov.pt', items[0]['link'])
        self.assertIn('Soma dos montantes', items[0]['summary'])
        self.assertIn('248,857.00 €', items[1]['summary'])

    def test_empty_or_garbage_returns_empty(self):
        self.assertEqual(parse_azores_digest(''), [])
        self.assertEqual(parse_azores_digest('   '), [])
        self.assertEqual(parse_azores_digest('<p>no list items</p>'), [])

    def test_li_without_anchor_is_skipped(self):
        html = """
        <ul>
          <li>No link here
            <ul><li>detail</li></ul>
          </li>
          <li><a href="https://example.com/item">Valid item</a>
            <ul><li>detail line</li></ul>
          </li>
        </ul>
        """
        items = parse_azores_digest(html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], 'Valid item')
