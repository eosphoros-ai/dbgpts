# All In One Entrance

A chatbot based on intent recognition and slot filling as a entrance to all other chatbots.

![GIF](https://private-user-images.githubusercontent.com/17919400/335150728-b7ca8137-356f-43aa-96dd-44ad1b022e94.gif?jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3MTcxMjMyMDgsIm5iZiI6MTcxNzEyMjkwOCwicGF0aCI6Ii8xNzkxOTQwMC8zMzUxNTA3MjgtYjdjYTgxMzctMzU2Zi00M2FhLTk2ZGQtNDRhZDFiMDIyZTk0LmdpZj9YLUFtei1BbGdvcml0aG09QVdTNC1ITUFDLVNIQTI1NiZYLUFtei1DcmVkZW50aWFsPUFLSUFWQ09EWUxTQTUzUFFLNFpBJTJGMjAyNDA1MzElMkZ1cy1lYXN0LTElMkZzMyUyRmF3czRfcmVxdWVzdCZYLUFtei1EYXRlPTIwMjQwNTMxVDAyMzUwOFomWC1BbXotRXhwaXJlcz0zMDAmWC1BbXotU2lnbmF0dXJlPWUzMzMyMTE1M2E0YTNmYTM0NzJlNmVlMTU0YWQxODhjMzE3Yjg4MWU2MzdlYjkwYWVmNGQ3ZDI4MTM5NmYxYzMmWC1BbXotU2lnbmVkSGVhZGVycz1ob3N0JmFjdG9yX2lkPTAma2V5X2lkPTAmcmVwb19pZD0wIn0.MfAs1hqwfJskUa0T2tretg3OpoF404b9J3Hy9BpBD3k)

The graph of DAG is shown below:

![Graph](../../assets/img/workflow/all_in_one_entrance_dag.png)

## Usage

How to use it in DB-GPT?  First, install the workflow:

```bash
dbgpt app install all-in-one-entrance -U
```

Then restart the DB-GPT server. You will see the `all_in_one_entrance` in the "AWEL Flow" page.