# R80 Dependency License Scan Report

Date: 2026-11-15
Scanner: `pip-licenses` via `uv run --with pip-licenses`

## 1. Runtime Dependencies (Default Install)

Scan command:
```bash
uv run --with pip-licenses pip-licenses --fail-on "GPL;AGPL;GNU General Public License;GNU Affero" --partial-match
```

Result: **PASS (0 GPL/AGPL dependencies)**

## 2. Optional Extra: `openai-agents`

Status: **pass**

### License Summary
```text
 Count  License                                            
 2      Apache Software License                            
 1      Apache Software License; MIT License               
 4      Apache-2.0                                         
 1      Apache-2.0 OR BSD-3-Clause                         
 3      BSD License                                        
 1      BSD-2-Clause                                       
 10     BSD-3-Clause                                       
 1      BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 
 1      ISC License (ISCL)                                 
 15     MIT                                                
 7      MIT License                                        
 1      MIT-0                                              
 1      Mozilla Public License 2.0 (MPL 2.0)               
 1      PSF-2.0                                            
 1      Python Software Foundation License                 

```

### Packages
| Name                      | Version    | License                                            |
|---------------------------|------------|----------------------------------------------------|
| Jinja2                    | 3.1.6      | BSD License                                        |
| MarkupSafe                | 3.0.4      | BSD-3-Clause                                       |
| PyJWT                     | 2.15.1     | MIT                                                |
| PyYAML                    | 6.0.3      | MIT License                                        |
| Pygments                  | 2.21.0     | BSD-2-Clause                                       |
| annotated-doc             | 0.0.5      | MIT                                                |
| annotated-types           | 0.8.0      | MIT                                                |
| anyio                     | 4.15.1     | MIT                                                |
| attrs                     | 26.1.0     | MIT                                                |
| certifi                   | 2026.10.23 | Mozilla Public License 2.0 (MPL 2.0)               |
| cffi                      | 2.1.1      | MIT-0                                              |
| click                     | 8.5.0      | BSD-3-Clause                                       |
| colorama                  | 0.4.6      | BSD License                                        |
| cryptography              | 50.0.2     | Apache-2.0 OR BSD-3-Clause                         |
| distro                    | 1.9.0      | Apache Software License                            |
| h11                       | 0.16.0     | MIT License                                        |
| httpcore                  | 1.0.9      | BSD-3-Clause                                       |
| httpcore2                 | 2.16.0     | BSD-3-Clause                                       |
| httpx                     | 0.28.1     | BSD License                                        |
| httpx2                    | 2.16.0     | BSD-3-Clause                                       |
| idna                      | 3.20       | BSD-3-Clause                                       |
| jiter                     | 0.14.0     | MIT                                                |
| jsonpath-ng               | 1.14.0     | Apache-2.0                                         |
| jsonschema                | 4.26.0     | MIT                                                |
| jsonschema-specifications | 2025.9.1   | MIT                                                |
| markdown-it-py            | 4.2.0      | MIT License                                        |
| mcp                       | 2.3.0      | MIT License                                        |
| mcp-types                 | 2.3.0      | MIT License                                        |
| mdurl                     | 0.1.2      | MIT License                                        |
| numpy                     | 2.5.4      | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| openai                    | 3.3.0      | Apache Software License                            |
| opentelemetry-api         | 1.45.2     | Apache-2.0                                         |
| pycparser                 | 3.12       | BSD-3-Clause                                       |
| pydantic                  | 2.14.1     | MIT                                                |
| pydantic_core             | 2.50.1     | MIT                                                |
| python-multipart          | 0.0.32     | Apache-2.0                                         |
| pywin32                   | 312        | Python Software Foundation License                 |
| referencing               | 0.37.0     | MIT                                                |
| rich                      | 14.3.4     | MIT License                                        |
| rpds-py                   | 2026.9.1   | MIT                                                |
| shellingham               | 1.5.4      | ISC License (ISCL)                                 |
| skeptic-agent             | 0.0.0      | Apache-2.0                                         |
| sniffio                   | 1.3.1      | Apache Software License; MIT License               |
| sse-starlette             | 3.6.0      | BSD-3-Clause                                       |
| starlette                 | 1.10.0     | BSD-3-Clause                                       |
| truststore                | 0.10.5     | MIT                                                |
| typer                     | 0.27.3     | MIT                                                |
| typing-inspection         | 0.4.4      | MIT                                                |
| typing_extensions         | 4.16.0     | PSF-2.0                                            |
| uvicorn                   | 0.54.0     | BSD-3-Clause                                       |


## 2. Optional Extra: `langgraph`

Status: **pass**

### License Summary
```text
 License  Count                                              
 1        Apache Software License; MIT License               
 1        Apache-2.0 OR BSD-3-Clause                         
 1        BSD-2-Clause                                       
 1        BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 
 1        ISC License (ISCL)                                 
 1        MIT-0                                              
 1        Mozilla Public License 2.0 (MPL 2.0)               
 1        PSF-2.0                                            
 1        Python Software Foundation License                 
 2        Apache Software License                            
 3        BSD License                                        
 4        Apache-2.0                                         
 7        MIT License                                        
 10       BSD-3-Clause                                       
 15       MIT                                                

```

### Packages
| Name                      | Version    | License                                            |
|---------------------------|------------|----------------------------------------------------|
| Jinja2                    | 3.1.6      | BSD License                                        |
| MarkupSafe                | 3.0.4      | BSD-3-Clause                                       |
| PyJWT                     | 2.15.1     | MIT                                                |
| PyYAML                    | 6.0.3      | MIT License                                        |
| Pygments                  | 2.21.0     | BSD-2-Clause                                       |
| annotated-doc             | 0.0.5      | MIT                                                |
| annotated-types           | 0.8.0      | MIT                                                |
| anyio                     | 4.15.1     | MIT                                                |
| attrs                     | 26.1.0     | MIT                                                |
| certifi                   | 2026.10.23 | Mozilla Public License 2.0 (MPL 2.0)               |
| cffi                      | 2.1.1      | MIT-0                                              |
| click                     | 8.5.0      | BSD-3-Clause                                       |
| colorama                  | 0.4.6      | BSD License                                        |
| cryptography              | 50.0.2     | Apache-2.0 OR BSD-3-Clause                         |
| distro                    | 1.9.0      | Apache Software License                            |
| h11                       | 0.16.0     | MIT License                                        |
| httpcore                  | 1.0.9      | BSD-3-Clause                                       |
| httpcore2                 | 2.16.0     | BSD-3-Clause                                       |
| httpx                     | 0.28.1     | BSD License                                        |
| httpx2                    | 2.16.0     | BSD-3-Clause                                       |
| idna                      | 3.20       | BSD-3-Clause                                       |
| jiter                     | 0.14.0     | MIT                                                |
| jsonpath-ng               | 1.14.0     | Apache-2.0                                         |
| jsonschema                | 4.26.0     | MIT                                                |
| jsonschema-specifications | 2025.9.1   | MIT                                                |
| markdown-it-py            | 4.2.0      | MIT License                                        |
| mcp                       | 2.3.0      | MIT License                                        |
| mcp-types                 | 2.3.0      | MIT License                                        |
| mdurl                     | 0.1.2      | MIT License                                        |
| numpy                     | 2.5.4      | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| openai                    | 3.3.0      | Apache Software License                            |
| opentelemetry-api         | 1.45.2     | Apache-2.0                                         |
| pycparser                 | 3.12       | BSD-3-Clause                                       |
| pydantic                  | 2.14.1     | MIT                                                |
| pydantic_core             | 2.50.1     | MIT                                                |
| python-multipart          | 0.0.32     | Apache-2.0                                         |
| pywin32                   | 312        | Python Software Foundation License                 |
| referencing               | 0.37.0     | MIT                                                |
| rich                      | 14.3.4     | MIT License                                        |
| rpds-py                   | 2026.9.1   | MIT                                                |
| shellingham               | 1.5.4      | ISC License (ISCL)                                 |
| skeptic-agent             | 0.0.0      | Apache-2.0                                         |
| sniffio                   | 1.3.1      | Apache Software License; MIT License               |
| sse-starlette             | 3.6.0      | BSD-3-Clause                                       |
| starlette                 | 1.10.0     | BSD-3-Clause                                       |
| truststore                | 0.10.5     | MIT                                                |
| typer                     | 0.27.3     | MIT                                                |
| typing-inspection         | 0.4.4      | MIT                                                |
| typing_extensions         | 4.16.0     | PSF-2.0                                            |
| uvicorn                   | 0.54.0     | BSD-3-Clause                                       |


## 2. Optional Extra: `crewai`

Status: **pass**

### License Summary
```text
 License  Count                                              
 1        Apache Software License; MIT License               
 1        Apache-2.0 OR BSD-3-Clause                         
 1        BSD-2-Clause                                       
 1        BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 
 1        ISC License (ISCL)                                 
 1        MIT-0                                              
 1        Mozilla Public License 2.0 (MPL 2.0)               
 1        PSF-2.0                                            
 1        Python Software Foundation License                 
 2        Apache Software License                            
 3        BSD License                                        
 4        Apache-2.0                                         
 7        MIT License                                        
 10       BSD-3-Clause                                       
 15       MIT                                                

```

### Packages
| Name                      | Version    | License                                            |
|---------------------------|------------|----------------------------------------------------|
| Jinja2                    | 3.1.6      | BSD License                                        |
| MarkupSafe                | 3.0.4      | BSD-3-Clause                                       |
| PyJWT                     | 2.15.1     | MIT                                                |
| PyYAML                    | 6.0.3      | MIT License                                        |
| Pygments                  | 2.21.0     | BSD-2-Clause                                       |
| annotated-doc             | 0.0.5      | MIT                                                |
| annotated-types           | 0.8.0      | MIT                                                |
| anyio                     | 4.15.1     | MIT                                                |
| attrs                     | 26.1.0     | MIT                                                |
| certifi                   | 2026.10.23 | Mozilla Public License 2.0 (MPL 2.0)               |
| cffi                      | 2.1.1      | MIT-0                                              |
| click                     | 8.5.0      | BSD-3-Clause                                       |
| colorama                  | 0.4.6      | BSD License                                        |
| cryptography              | 50.0.2     | Apache-2.0 OR BSD-3-Clause                         |
| distro                    | 1.9.0      | Apache Software License                            |
| h11                       | 0.16.0     | MIT License                                        |
| httpcore                  | 1.0.9      | BSD-3-Clause                                       |
| httpcore2                 | 2.16.0     | BSD-3-Clause                                       |
| httpx                     | 0.28.1     | BSD License                                        |
| httpx2                    | 2.16.0     | BSD-3-Clause                                       |
| idna                      | 3.20       | BSD-3-Clause                                       |
| jiter                     | 0.14.0     | MIT                                                |
| jsonpath-ng               | 1.14.0     | Apache-2.0                                         |
| jsonschema                | 4.26.0     | MIT                                                |
| jsonschema-specifications | 2025.9.1   | MIT                                                |
| markdown-it-py            | 4.2.0      | MIT License                                        |
| mcp                       | 2.3.0      | MIT License                                        |
| mcp-types                 | 2.3.0      | MIT License                                        |
| mdurl                     | 0.1.2      | MIT License                                        |
| numpy                     | 2.5.4      | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| openai                    | 3.3.0      | Apache Software License                            |
| opentelemetry-api         | 1.45.2     | Apache-2.0                                         |
| pycparser                 | 3.12       | BSD-3-Clause                                       |
| pydantic                  | 2.14.1     | MIT                                                |
| pydantic_core             | 2.50.1     | MIT                                                |
| python-multipart          | 0.0.32     | Apache-2.0                                         |
| pywin32                   | 312        | Python Software Foundation License                 |
| referencing               | 0.37.0     | MIT                                                |
| rich                      | 14.3.4     | MIT License                                        |
| rpds-py                   | 2026.9.1   | MIT                                                |
| shellingham               | 1.5.4      | ISC License (ISCL)                                 |
| skeptic-agent             | 0.0.0      | Apache-2.0                                         |
| sniffio                   | 1.3.1      | Apache Software License; MIT License               |
| sse-starlette             | 3.6.0      | BSD-3-Clause                                       |
| starlette                 | 1.10.0     | BSD-3-Clause                                       |
| truststore                | 0.10.5     | MIT                                                |
| typer                     | 0.27.3     | MIT                                                |
| typing-inspection         | 0.4.4      | MIT                                                |
| typing_extensions         | 4.16.0     | PSF-2.0                                            |
| uvicorn                   | 0.54.0     | BSD-3-Clause                                       |


## 2. Optional Extra: `pydantic-ai`

Status: **pass**

### License Summary
```text
 Count  License                                            
 2      Apache Software License                            
 1      Apache Software License; MIT License               
 4      Apache-2.0                                         
 1      Apache-2.0 OR BSD-3-Clause                         
 3      BSD License                                        
 1      BSD-2-Clause                                       
 10     BSD-3-Clause                                       
 1      BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 
 1      ISC License (ISCL)                                 
 15     MIT                                                
 7      MIT License                                        
 1      MIT-0                                              
 1      Mozilla Public License 2.0 (MPL 2.0)               
 1      PSF-2.0                                            
 1      Python Software Foundation License                 

```

### Packages
| Name                      | Version    | License                                            |
|---------------------------|------------|----------------------------------------------------|
| Jinja2                    | 3.1.6      | BSD License                                        |
| MarkupSafe                | 3.0.4      | BSD-3-Clause                                       |
| PyJWT                     | 2.15.1     | MIT                                                |
| PyYAML                    | 6.0.3      | MIT License                                        |
| Pygments                  | 2.21.0     | BSD-2-Clause                                       |
| annotated-doc             | 0.0.5      | MIT                                                |
| annotated-types           | 0.8.0      | MIT                                                |
| anyio                     | 4.15.1     | MIT                                                |
| attrs                     | 26.1.0     | MIT                                                |
| certifi                   | 2026.10.23 | Mozilla Public License 2.0 (MPL 2.0)               |
| cffi                      | 2.1.1      | MIT-0                                              |
| click                     | 8.5.0      | BSD-3-Clause                                       |
| colorama                  | 0.4.6      | BSD License                                        |
| cryptography              | 50.0.2     | Apache-2.0 OR BSD-3-Clause                         |
| distro                    | 1.9.0      | Apache Software License                            |
| h11                       | 0.16.0     | MIT License                                        |
| httpcore                  | 1.0.9      | BSD-3-Clause                                       |
| httpcore2                 | 2.16.0     | BSD-3-Clause                                       |
| httpx                     | 0.28.1     | BSD License                                        |
| httpx2                    | 2.16.0     | BSD-3-Clause                                       |
| idna                      | 3.20       | BSD-3-Clause                                       |
| jiter                     | 0.14.0     | MIT                                                |
| jsonpath-ng               | 1.14.0     | Apache-2.0                                         |
| jsonschema                | 4.26.0     | MIT                                                |
| jsonschema-specifications | 2025.9.1   | MIT                                                |
| markdown-it-py            | 4.2.0      | MIT License                                        |
| mcp                       | 2.3.0      | MIT License                                        |
| mcp-types                 | 2.3.0      | MIT License                                        |
| mdurl                     | 0.1.2      | MIT License                                        |
| numpy                     | 2.5.4      | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| openai                    | 3.3.0      | Apache Software License                            |
| opentelemetry-api         | 1.45.2     | Apache-2.0                                         |
| pycparser                 | 3.12       | BSD-3-Clause                                       |
| pydantic                  | 2.14.1     | MIT                                                |
| pydantic_core             | 2.50.1     | MIT                                                |
| python-multipart          | 0.0.32     | Apache-2.0                                         |
| pywin32                   | 312        | Python Software Foundation License                 |
| referencing               | 0.37.0     | MIT                                                |
| rich                      | 14.3.4     | MIT License                                        |
| rpds-py                   | 2026.9.1   | MIT                                                |
| shellingham               | 1.5.4      | ISC License (ISCL)                                 |
| skeptic-agent             | 0.0.0      | Apache-2.0                                         |
| sniffio                   | 1.3.1      | Apache Software License; MIT License               |
| sse-starlette             | 3.6.0      | BSD-3-Clause                                       |
| starlette                 | 1.10.0     | BSD-3-Clause                                       |
| truststore                | 0.10.5     | MIT                                                |
| typer                     | 0.27.3     | MIT                                                |
| typing-inspection         | 0.4.4      | MIT                                                |
| typing_extensions         | 4.16.0     | PSF-2.0                                            |
| uvicorn                   | 0.54.0     | BSD-3-Clause                                       |


## 2. Optional Extra: `dev`

Status: **pass**

### License Summary
```text
 Count  License                                            
 2      Apache Software License                            
 1      Apache Software License; MIT License               
 4      Apache-2.0                                         
 1      Apache-2.0 OR BSD-3-Clause                         
 3      BSD License                                        
 1      BSD-2-Clause                                       
 10     BSD-3-Clause                                       
 1      BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 
 1      ISC License (ISCL)                                 
 15     MIT                                                
 7      MIT License                                        
 1      MIT-0                                              
 1      Mozilla Public License 2.0 (MPL 2.0)               
 1      PSF-2.0                                            
 1      Python Software Foundation License                 

```

### Packages
| Name                      | Version    | License                                            |
|---------------------------|------------|----------------------------------------------------|
| Jinja2                    | 3.1.6      | BSD License                                        |
| MarkupSafe                | 3.0.4      | BSD-3-Clause                                       |
| PyJWT                     | 2.15.1     | MIT                                                |
| PyYAML                    | 6.0.3      | MIT License                                        |
| Pygments                  | 2.21.0     | BSD-2-Clause                                       |
| annotated-doc             | 0.0.5      | MIT                                                |
| annotated-types           | 0.8.0      | MIT                                                |
| anyio                     | 4.15.1     | MIT                                                |
| attrs                     | 26.1.0     | MIT                                                |
| certifi                   | 2026.10.23 | Mozilla Public License 2.0 (MPL 2.0)               |
| cffi                      | 2.1.1      | MIT-0                                              |
| click                     | 8.5.0      | BSD-3-Clause                                       |
| colorama                  | 0.4.6      | BSD License                                        |
| cryptography              | 50.0.2     | Apache-2.0 OR BSD-3-Clause                         |
| distro                    | 1.9.0      | Apache Software License                            |
| h11                       | 0.16.0     | MIT License                                        |
| httpcore                  | 1.0.9      | BSD-3-Clause                                       |
| httpcore2                 | 2.16.0     | BSD-3-Clause                                       |
| httpx                     | 0.28.1     | BSD License                                        |
| httpx2                    | 2.16.0     | BSD-3-Clause                                       |
| idna                      | 3.20       | BSD-3-Clause                                       |
| jiter                     | 0.14.0     | MIT                                                |
| jsonpath-ng               | 1.14.0     | Apache-2.0                                         |
| jsonschema                | 4.26.0     | MIT                                                |
| jsonschema-specifications | 2025.9.1   | MIT                                                |
| markdown-it-py            | 4.2.0      | MIT License                                        |
| mcp                       | 2.3.0      | MIT License                                        |
| mcp-types                 | 2.3.0      | MIT License                                        |
| mdurl                     | 0.1.2      | MIT License                                        |
| numpy                     | 2.5.4      | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| openai                    | 3.3.0      | Apache Software License                            |
| opentelemetry-api         | 1.45.2     | Apache-2.0                                         |
| pycparser                 | 3.12       | BSD-3-Clause                                       |
| pydantic                  | 2.14.1     | MIT                                                |
| pydantic_core             | 2.50.1     | MIT                                                |
| python-multipart          | 0.0.32     | Apache-2.0                                         |
| pywin32                   | 312        | Python Software Foundation License                 |
| referencing               | 0.37.0     | MIT                                                |
| rich                      | 14.3.4     | MIT License                                        |
| rpds-py                   | 2026.9.1   | MIT                                                |
| shellingham               | 1.5.4      | ISC License (ISCL)                                 |
| skeptic-agent             | 0.0.0      | Apache-2.0                                         |
| sniffio                   | 1.3.1      | Apache Software License; MIT License               |
| sse-starlette             | 3.6.0      | BSD-3-Clause                                       |
| starlette                 | 1.10.0     | BSD-3-Clause                                       |
| truststore                | 0.10.5     | MIT                                                |
| typer                     | 0.27.3     | MIT                                                |
| typing-inspection         | 0.4.4      | MIT                                                |
| typing_extensions         | 4.16.0     | PSF-2.0                                            |
| uvicorn                   | 0.54.0     | BSD-3-Clause                                       |


