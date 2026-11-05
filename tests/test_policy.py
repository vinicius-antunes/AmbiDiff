"""URL/destino são evidências distintas de funcionamento; nenhuma rede."""
import pytest
from ambidiff_next.policy import normalize_url,safe_url,allowed_url,equivalent_url,redact_url,classify_resource

ROOTS=('https://portal.invalid/','https://homol.invalid/web/orgao')


@pytest.mark.parametrize('bad',['javascript:alert(1)','http://user:pass@portal.invalid/','http://[invalid','https://bad host/','https://portal.invalid:bad/','https://portal.invalid/../logout','https://a.-invalid/'])
def test_invalid_urls_rejected(bad):
    with pytest.raises(ValueError):normalize_url(bad)


def test_url_equivalence_preserves_functional_query_fragment_and_subpath():
    assert equivalent_url('https://portal.invalid/consulta?c=1&e=2#t','https://homol.invalid/web/orgao/consulta?c=1&e=2#t',ROOTS)
    assert not equivalent_url('https://portal.invalid/consulta?c=1','https://homol.invalid/web/orgao/consulta?c=2',ROOTS)
    assert not equivalent_url('https://portal.invalid/consulta#a','https://homol.invalid/web/orgao/consulta#b',ROOTS)
    assert not allowed_url('https://homol.invalid/web/outro',ROOTS[1])
    assert not allowed_url('https://homol.invalid/web/orgao2',ROOTS[1])
    assert equivalent_url('https://externo.invalid/x','https://externo.invalid/x',ROOTS)
    assert not equivalent_url('https://externo.invalid/x','https://externo.invalid/y',ROOTS)


@pytest.mark.parametrize('url',['https://portal.invalid/logout','https://portal.invalid/excluir/12','https://portal.invalid/?action=delete','https://portal.invalid/?p_p_lifecycle=1','https://portal.invalid/?p_auth=secret','https://portal.invalid/?operation=save','https://portal.invalid/%252e%252e/logout'])
def test_get_is_not_necessarily_safe(url):assert not safe_url(url)


def test_no_query_values_in_diagnostic_url():
    u=redact_url('https://portal.invalid/consulta?c=123&token=topsecret#secret')
    assert 'topsecret' not in u and '123' not in u and '#secret' not in u
    assert 'token' in u


def test_document_media_and_uncertainty_are_distinct():
    assert classify_resource('https://portal.invalid/doc.pdf')=='document'
    assert classify_resource('https://portal.invalid/documents/d/org/boletim')=='document_reference'
    assert classify_resource('https://portal.invalid/documents/d/org/foto',{'mime':'image/jpeg'})=='media'
    assert classify_resource('https://portal.invalid/documents/d/org/boletim',{'mime':'application/pdf'})=='document'
    assert classify_resource('https://www.google.com/recaptcha/api.js')=='auxiliary'
