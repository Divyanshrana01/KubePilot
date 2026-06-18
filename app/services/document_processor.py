from pathlib import Path

from docling.chunking import HybridChunker
from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from loguru import logger

#this class takes a pdf file and splits it into smaller chunks ready to be embedded.
#it uses docling to parse the pdf and then splits it up using a hybrid chunker.
class DocumentProcessor:
    def __init__(self):
        #set up the pdf pipeline to use apple silicon MPS for faster processing
        pipeline_options = PdfPipelineOptions()
        # MPS doesn't support float64 which docling's layout model requires — use CPU instead.
        pipeline_options.accelerator_options = AcceleratorOptions(
            num_threads=8, device=AcceleratorDevice.CPU
        )
        #the converter handles the actual pdf parsing
        self.converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
        #the hybrid chunker splits the parsed document into sensible text chunks
        self.chunker = HybridChunker()

    #this fn takes a file path, parses the pdf, and returns a list of chunks.
    #each chunk is a dict with the text content, the source filename, and optionally the page number.
    def process_document(self, file_path: str) -> list[dict]:
        result = self.converter.convert(file_path)
        doc = result.document
        chunk_iter = self.chunker.chunk(doc)

        chunks = []
        source_name = Path(file_path).name

        for chunk in chunk_iter:
            meta = {"text": chunk.text, "source": source_name}
            #try to pull the page number from the chunk metadata if it's available
            if hasattr(chunk, "meta") and hasattr(chunk.meta, "doc_items"):
                items = chunk.meta.doc_items
                if items and hasattr(items[0], "prov") and items[0].prov:
                    meta["page_number"] = items[0].prov[0].page_no
            chunks.append(meta)
        logger.info("Processed {} chunks from {}", len(chunks), file_path)
        return chunks
