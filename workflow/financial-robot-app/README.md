# Financial Robot App

## Chat with the Financial Robot Locally

Before you can chat with the financial robot, you need to have the financial report 
knowledge extracted according to the 
[Financial Report Knowledge Factory](../financial-report-knowledge-factory/README.md) workflow.


Chat with the financial robot using the following command:

```bash
dbgpt run flow --local \
--file workflow/financial-robot-app/financial_robot_app/__init__.py \
chat \
--name financial-robot-app \
--model "gpt-3.5-turbo" \
--extra '{
    "space": "my_knowledge_space",
    "db_name": "my_knowledge_space_fin_report",
    "embedding_model": "/opt/model_links/bge-large-zh-v1.5/"
}' \
--stream \
--messages "你好啊"
```

Here we use the `bge-large-zh-v1.5` model, please replace the path with the actual path
to the model on your machine.

```bash
dbgpt run flow --local --file workflow/financial-robot-app/financial_robot_app/__init__.py \
chat \
--name financial-robot-app \
--model "gpt-3.5-turbo" \
--extra '{
    "space": "my_knowledge_space",
    "db_name": "my_knowledge_space_fin_report",
    "embedding_model": "/opt/model_links/bge-large-zh-v1.5/"
}' \
--stream \
--messages "贵州航天电器法定代表是谁"
```

```bash
dbgpt run flow --local --file workflow/financial-robot-app/financial_robot_app/__init__.py \
chat \
--name financial-robot-app \
--model "gpt-3.5-turbo" \
--extra '{
    "space": "my_knowledge_space",
    "db_name": "my_knowledge_space_fin_report",
    "embedding_model": "/opt/model_links/bge-large-zh-v1.5/"
}' \
--stream \
--messages "分析下广州惠威电声研发投入情况"
```

```bash
dbgpt run flow --local --file workflow/financial-robot-app/financial_robot_app/__init__.py \
chat \
--name financial-robot-app \
--model "gpt-3.5-turbo" \
--extra '{
    "space": "my_knowledge_space",
    "db_name": "my_knowledge_space_fin_report",
    "embedding_model": "/opt/model_links/bge-large-zh-v1.5/"
}' \
--stream \
--messages "贵州航天公司毛利率是多少"
```

```bash
dbgpt run flow --local --file workflow/financial-robot-app/financial_robot_app/__init__.py \
chat \
--name financial-robot-app \
--model "gpt-3.5-turbo" \
--extra '{
    "space": "my_knowledge_space",
    "db_name": "my_knowledge_space_fin_report",
    "embedding_model": "/opt/model_links/bge-large-zh-v1.5/"
}' \
--stream \
--messages "广州惠威电声资产负债率是多少"
```

```bash
dbgpt run flow --local \
--file workflow/financial-robot-app/financial_robot_app/__init__.py \
chat \
--name financial-robot-app \
--model "gpt-3.5-turbo" \
--extra '{
    "space": "my_knowledge_space",
    "db_name": "my_knowledge_space_fin_report",
    "embedding_model": "/opt/model_links/bge-large-zh-v1.5/"
}' \
--stream \
--messages "你会干嘛？" \
-i
```

## Chat with the Financial Robot in DB-GPT

```bash
dbgpt app install financial-robot-app -U
```