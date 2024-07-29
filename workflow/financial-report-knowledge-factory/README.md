# Financial Report Knowledge Factory


The Financial Report Knowledge Factory is a workflow that extracts financial report 
knowledge from the PDF files. 


## Run the Financial Report Knowledge Factory Locally

Run the following command to extract the financial report knowledge from a PDF file:

```bash
dbgpt run flow --local \
--file workflow/financial-report-knowledge-factory/financial_report_knowledge_factory/__init__.py \
cmd \
--name financial-report-knowledge-factory \
-d '
{
    "space": "my_knowledge_space",
    "file_path": "./assets/pdf/financial-reports/2020-04-14__贵州航天电器股份有限公司__002025__航天电器__2019年__年度报告.pdf",
    "embedding_model": "/opt/model_links/bge-large-zh-v1.5/"
}'
```

The `file_path` is the path to the PDF file you want to extract the financial report 
knowledge from. The `embedding_model` is the path to the embedding model used to 
extract the financial report knowledge, here we use the `bge-large-zh-v1.5` model, please
replace the path with the actual path to the model on your machine.

The parsed data will be saved in the `./output/my_knowledge_space` directory.

Let's import another PDF file and extract the financial report knowledge from it:

```bash
dbgpt run flow --local \
--file workflow/financial-report-knowledge-factory/financial_report_knowledge_factory/__init__.py \
cmd \
--name financial-report-knowledge-factory \
-d '
{
    "space": "my_knowledge_space",
    "file_path": "./assets/pdf/financial-reports/2020-04-15__广州惠威电声科技股份有限公司__002888__惠威科技__2019年__年度报告.pdf",
    "embedding_model": "/opt/model_links/bge-large-zh-v1.5/"
}'
```

## Chat with the Financial Report

See the [Chat with the Financial Report](../financial-robot-app/README.md) section in the
Financial Robot App README for more information on how to chat with the financial report.

## Install the Financial Report Knowledge Factory as an App In Your DB-GPT

```bash
dbgpt app install financial-report-knowledge-factory -U
```