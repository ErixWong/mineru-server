"""MinerU Worker Script

Called by subprocess to process PDF files.
This script runs in its own process, avoiding multiprocessing nesting issues.
"""

import sys
import json
from pathlib import Path

if __name__ == '__main__':
    # Read config from stdin
    config = json.load(sys.stdin)
    
    # Import MinerU
    from mineru.cli.common import do_parse
    
    # Read PDF bytes from file
    pdf_path = Path(config['pdf_path'])
    pdf_bytes = pdf_path.read_bytes()
    
    # Call do_parse
    do_parse(
        output_dir=config['output_dir'],
        pdf_file_names=config['pdf_file_names'],
        pdf_bytes_list=[pdf_bytes],
        p_lang_list=config['p_lang_list'],
        backend=config['backend'],
        parse_method=config.get('parse_method', 'auto'),
        formula_enable=config.get('formula_enable', True),
        table_enable=config.get('table_enable', True),
        image_analysis=config.get('image_analysis', True),
        start_page_id=config.get('start_page_id', 0),
        end_page_id=config.get('end_page_id', None),
        server_url=config.get('server_url'),
        f_dump_md=True,
        f_dump_middle_json=True,
        f_dump_model_output=False,
        f_dump_content_list=True,
        f_make_md_mode="mm_markdown",
    )
    
    print("DONE")