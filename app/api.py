from pathlib import Path
import logging
from typing import Callable
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .logging_utils import bind_log_context, configure_logging, log_exception, log_info, log_warning, reset_log_context
from .planalto import processar_planalto
from .sudoeste import processar_sudoeste
from .sudoeste_consolidado import processar_sudoeste_consolidado
from .sudoeste_direto import processar_sudoeste_direto
from .sudoeste_indireto import processar_sudoeste_indireto
from .sudoeste_processadov2 import processar_sudoeste_processadov2

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI()

EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Para frontend e backend em origens diferentes no futuro:
# from fastapi.middleware.cors import CORSMiddleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://127.0.0.1:3000"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


# essa função é responsável por extrair o nome do arquivo 
# enviado, garantindo que seja um nome válido e 
# não apenas espaços em branco. Se o upload for None ou o
# nome do arquivo for vazio, ela retorna None.
def _extract_file_name(upload: UploadFile | None) -> str | None:
    if upload is None:
        return None
    if upload.filename and upload.filename.strip():
        return upload.filename
    return None


# essa função verifica quais campos de upload estão ausentes, ou seja, quais uploads são None 
# ou têm nomes de arquivos inválidos. Ela retorna uma lista dos nomes dos campos que estão 
# faltando, o que é útil para validar a entrada do usuário e fornecer feedback claro sobre 
# quais arquivos precisam ser enviados.
def _get_missing_fields(uploads: dict[str, UploadFile | None]) -> list[str]:
    return [field for field, upload in uploads.items() if _extract_file_name(upload) is None]




async def _read_upload_bytes(
    fluxo: str,
    request_id: str,
    field_name: str,
    upload: UploadFile,
) -> bytes:
    try:
        content = await upload.read()
    except Exception:
        log_exception(
            logger,
            "Falha ao ler arquivo enviado",
            fluxo=fluxo,
            campo=field_name,
            arquivo=upload.filename,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Nao foi possivel ler o arquivo '{field_name}' no fluxo {fluxo}. request_id={request_id}",
        )

    log_info(
        logger,
        "Arquivo lido com sucesso",
        fluxo=fluxo,
        campo=field_name,
        arquivo=upload.filename,
        tamanho_bytes=len(content),
        content_type=upload.content_type,
    )
    return content


async def _executar_fluxo_upload(
    fluxo: str,
    uploads: dict[str, UploadFile | None],
    processor: Callable[..., object],
    output_filename: str,
    output_media_type: str = EXCEL_MEDIA_TYPE,
    multipart_keys: list[str] | None = None,
    processor_param_map: dict[str, str] | None = None,
) -> StreamingResponse:
    request_id = uuid.uuid4().hex
    context_token = bind_log_context(request_id=request_id, fluxo=fluxo)

    try:
        expected_fields = list(uploads.keys())
        received_files = {field: _extract_file_name(upload) for field, upload in uploads.items()}

        log_info(
            logger,
            "Recebida requisicao de processamento",
            campos_esperados=expected_fields,
        )
        log_info(
            logger,
            "Arquivos recebidos na requisicao",
            arquivos=received_files,
        )
        if multipart_keys is not None:
            log_info(
                logger,
                "Chaves multipart recebidas na requisicao",
                chaves_multipart=multipart_keys,
            )
            unexpected_keys = [key for key in multipart_keys if key not in expected_fields]
            if unexpected_keys:
                log_warning(
                    logger,
                    "Chaves multipart inesperadas detectadas",
                    chaves_inesperadas=unexpected_keys,
                    chaves_aceitas=expected_fields,
                )

        missing_fields = _get_missing_fields(uploads)
        if missing_fields:
            detail = (
                f"Fluxo {fluxo} recebeu campos incompletos. "
                f"Faltando: {', '.join(missing_fields)}. request_id={request_id}"
            )
            log_warning(
                logger,
                "Campos ausentes na requisicao",
                campos_ausentes=missing_fields,
            )
            raise HTTPException(status_code=422, detail=detail)

        log_info(logger, "Validacao de campos obrigatorios concluida")

        try:
            payload = {
                field_name: await _read_upload_bytes(fluxo, request_id, field_name, upload)
                for field_name, upload in uploads.items()
                if upload is not None
            }
            param_map = processor_param_map or {field_name: field_name for field_name in payload.keys()}
            missing_map_fields = sorted({source_field for source_field in param_map.values() if source_field not in payload})
            if missing_map_fields:
                log_warning(
                    logger,
                    "Mapeamento de parametros do processador incompleto",
                    campos_mapeados_ausentes=missing_map_fields,
                    mapeamento=param_map,
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Erro interno ao processar fluxo {fluxo}. request_id={request_id}",
                )

            processor_kwargs = {
                processor_param: payload[source_field]
                for processor_param, source_field in param_map.items()
            }

            log_info(
                logger,
                "Mapeamento de parametros para o processador",
                mapeamento=param_map,
            )
            log_info(logger, "Iniciando processamento do fluxo")

            resultado = processor(**processor_kwargs)
            output_size = len(resultado.getbuffer()) if hasattr(resultado, "getbuffer") else None

            log_info(
                logger,
                "Processamento concluido com sucesso",
                arquivo_saida=output_filename,
                tamanho_saida_bytes=output_size,
            )

            return StreamingResponse(
                resultado,
                media_type=output_media_type,
                headers={
                    "Content-Disposition": f"attachment; filename={output_filename}",
                    "X-Request-ID": request_id,
                },
            )
        except HTTPException:
            raise
        except Exception:
            log_exception(logger, "Erro ao processar fluxo")
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Erro interno ao processar fluxo {fluxo}. "
                    f"Verifique os arquivos enviados. request_id={request_id}"
                ),
            )
    finally:
        reset_log_context(context_token)


@app.post("/planalto")
async def planalto(
    request: Request,
    recebimento: UploadFile | None = File(None),
    pagamento: UploadFile | None = File(None),
):
    multipart_keys = list((await request.form()).keys())
    return await _executar_fluxo_upload(
        fluxo="planalto",
        uploads={"recebimento": recebimento, "pagamento": pagamento},
        processor=processar_planalto,
        output_filename="planalto_processado.xlsx",
        multipart_keys=multipart_keys,
        processor_param_map={
            "recebimento": "recebimento",
            "pagamento": "pagamento",
        },
    )


@app.post("/sudoeste")
async def sudoeste(
    request: Request,
    base: UploadFile | None = File(None),
    recebimento: UploadFile | None = File(None),
    denodo: UploadFile | None = File(None),
):
    multipart_keys = list((await request.form()).keys())
    return await _executar_fluxo_upload(
        fluxo="sudoeste-inicial",
        uploads={"base": base, "recebimento": recebimento, "denodo": denodo},
        processor=processar_sudoeste,
        output_filename="sudoeste_inicial_processado.xlsx",
        multipart_keys=multipart_keys,
        processor_param_map={
            "base_excel": "base",
            "recebimento_excel": "recebimento",
            "denodo_excel": "denodo",
        },
    )


@app.post("/sudoeste-direto")
async def sudoeste_direto(
    request: Request,
    processada: UploadFile | None = File(None),
    direta: UploadFile | None = File(None),
):
    multipart_keys = list((await request.form()).keys())
    return await _executar_fluxo_upload(
        fluxo="sudoeste-direto",
        uploads={"processada": processada, "direta": direta},
        processor=processar_sudoeste_direto,
        output_filename="sudoeste_direto_processado.xlsx",
        multipart_keys=multipart_keys,
        processor_param_map={
            "processada_excel": "processada",
            "direta_excel": "direta",
        },
    )


@app.post("/sudoeste-indireto")
async def sudoeste_indireto(
    request: Request,
    processada: UploadFile | None = File(None),
    indireto: UploadFile | None = File(None),
):
    multipart_keys = list((await request.form()).keys())
    return await _executar_fluxo_upload(
        fluxo="sudoeste-indireto",
        uploads={"processada": processada, "indireto": indireto},
        processor=processar_sudoeste_indireto,
        output_filename="sudoeste_indireto_processado.xlsx",
        multipart_keys=multipart_keys,
        processor_param_map={
            "processada_excel": "processada",
            "indireto_excel": "indireto",
        },
    )


@app.post("/sudoeste-consolidado")
async def sudoeste_consolidado(
    request: Request,
    processada: UploadFile | None = File(None),
    direta: UploadFile | None = File(None),
    indireto: UploadFile | None = File(None),
):
    multipart_keys = list((await request.form()).keys())
    return await _executar_fluxo_upload(
        fluxo="sudoeste-consolidado",
        uploads={"processada": processada, "direta": direta, "indireto": indireto},
        processor=processar_sudoeste_consolidado,
        output_filename="sudoeste_consolidado_processado.xlsx",
        multipart_keys=multipart_keys,
        processor_param_map={
            "processada_excel": "processada",
            "direta_excel": "direta",
            "indireto_excel": "indireto",
        },
    )


@app.post("/sudoeste-processado-v2")
async def sudoeste_processado_v2(
    request: Request,
    inicial_processado: UploadFile | None = File(None),
    direto: UploadFile | None = File(None),
    indireto: UploadFile | None = File(None),
):
    multipart_keys = list((await request.form()).keys())
    return await _executar_fluxo_upload(
        fluxo="sudoeste-processado-v2",
        uploads={
            "inicial_processado": inicial_processado,
            "direto": direto,
            "indireto": indireto,
        },
        processor=processar_sudoeste_processadov2,
        output_filename="sudoeste_processado_v2.xlsx",
        multipart_keys=multipart_keys,
        processor_param_map={
            "inicial_processado_excel": "inicial_processado",
            "direto_excel": "direto",
            "indireto_excel": "indireto",
        },
    )
