"""MinerU worker script.

Called by subprocess to process PDF files. This script runs in its own process,
avoiding multiprocessing nesting issues.
"""

import json
import os
import sys
from pathlib import Path

from mineru_mcp.mineru_adapter import run_parse

if __name__ == '__main__':
    try:
        config = json.load(sys.stdin)

        pdf_path = Path(config['pdf_path'])
        pdf_bytes = pdf_path.read_bytes()

        max_concurrency = config.get('max_concurrency')
        if max_concurrency is None:
            env_max_concurrency = os.getenv("MINERU_VLM_MAX_CONCURRENCY")
            if env_max_concurrency:
                try:
                    max_concurrency = int(env_max_concurrency)
                except ValueError:
                    max_concurrency = None

        server_headers = None
        vlm_api_key = config.get('vlm_api_key')
        if vlm_api_key:
            server_headers = {"Authorization": f"Bearer {vlm_api_key}"}

        run_parse(
            output_dir=config['output_dir'],
            pdf_file_names=config['pdf_file_names'],
            pdf_bytes_list=[pdf_bytes],
            p_lang_list=config['p_lang_list'],
            backend=config['backend'],
            parse_method=config.get('parse_method', 'auto'),
            formula_enable=config.get('formula_enable', True),
            table_enable=config.get('table_enable', True),
            image_analysis=config.get('image_analysis', True),
            max_concurrency=max_concurrency,
            start_page_id=config.get('start_page_id', 0),
            end_page_id=config.get('end_page_id', None),
            server_url=config.get('server_url'),
            server_headers=server_headers,
            model_name=config.get('vlm_model'),
            f_dump_md=True,
            f_dump_middle_json=True,
            f_dump_model_output=True,
            f_dump_content_list=True,
            f_make_md_mode="mm_markdown",
        )
        
        print("DONE")
        
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON config: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        # 上游（含 mineru HybridDependencyError）常通过 raise ... from exc 链接真实异常，
        # 仅打印 e 会掩盖根因（如 ModuleNotFoundError），排障需要完整因果链
        detail = str(e)
        cause = e.__cause__
        while cause is not None:
            detail += f" [caused by: {type(cause).__name__}: {cause}]"
            cause = cause.__cause__
        print(f"ERROR: MinerU runtime error: {detail}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"ERROR: File not found: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
