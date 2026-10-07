import argparse
import sys
import logging
from pipeline.orchestrator import parse_document
from output.json_writer import write_json
from output.markdown_writer import write_markdown

def main():
    parser = argparse.ArgumentParser(description="ParseAnything CLI (P1 Pipeline)")
    parser.add_argument("file_path", help="Path to the document to process")
    parser.add_argument("--out-json", help="Path to output JSON result")
    parser.add_argument("--out-md", help="Path to output Markdown result")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()

    # Configure logging
    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    print(f"Processing {args.file_path}...")
    
    # Run the pipeline
    doc_result = parse_document(args.file_path)
    
    if args.out_json:
        write_json(doc_result, args.out_json)
        print(f"[OK] JSON saved to {args.out_json}")
    
    if args.out_md:
        write_markdown(doc_result, args.out_md)
        print(f"[OK] Markdown saved to {args.out_md}")
        
    if doc_result.status == "failed":
        print("[FAILED] Parsing failed with the following errors:")
        for error in doc_result.errors:
            print(f"   [{error.get('error_code')}] {error.get('message')}")
        sys.exit(1)
    else:
        print(f"[DONE] Parsing completed successfully in {doc_result.metrics.get('total_time_seconds', 0)}s!")

if __name__ == "__main__":
    main()
