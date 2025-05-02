import base64
import os
import time
from pathlib import Path
from typing import Dict, Optional
import requests
import json
import gradio as gr
import uuid
from typing import Union


def encode_image(img_path):
    if not img_path:
        return None
    with open(img_path, "rb") as fin:
        image_data = base64.b64encode(fin.read()).decode("utf-8")
    return image_data


def get_latest_files(directory: str, file_types: list = ['.webm', '.zip']) -> Dict[str, Optional[str]]:
    """Get the latest recording and trace files"""
    latest_files: Dict[str, Optional[str]] = {ext: None for ext in file_types}

    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
        return latest_files

    for file_type in file_types:
        try:
            matches = list(Path(directory).rglob(f"*{file_type}"))
            if matches:
                latest = max(matches, key=lambda p: p.stat().st_mtime)
                # Only return files that are complete (not being written)
                if time.time() - latest.stat().st_mtime > 1.0:
                    latest_files[file_type] = str(latest)
        except Exception as e:
            print(f"Error getting latest {file_type} file: {e}")

    return latest_files

async def get_visual_marker_for_xpath(page, xpath: str) -> Union[dict, str]:
	try:
		script = """
            (xpath) => {
                function getElementByXPath(path) {
                    return document.evaluate(path, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                }
                
                function findFirstSVGInSubtree(element) {
                    // First try to find SVG elements
                    const svg = element.querySelector('svg');
                    if (svg) {
                        const box = svg.getAttribute('viewBox');
                        return {
                            type: 'svg',
                            class: svg.getAttribute('class') || '',
                            xpath: getXPath(svg)
                        };
                    }
                    
                    // Then try to find img elements
                    const img = element.querySelector('img');
                    if (img) {
                        return {
                            type: 'img',
                            class: img.getAttribute('class') || '',
                            xpath: getXPath(img)
                        };
                    }
                    
                    // Finally look for elements with icon classes
                    const iconElement = element.querySelector('[class*="icon"], [class*="octicon"], [class*="fa-"]');
                    if (iconElement) {
                        return {
                            type: 'icon',
                            class: iconElement.getAttribute('class') || '',
                            xpath: getXPath(iconElement)
                        };
                    }
                    
                    return null;
                }
                
                function getXPath(element) {
                    if (!element) return '';
                    if (element.id) return `//*[@id="${element.id}"]`;
                    
                    const parts = [];
                    while (element && element.nodeType === Node.ELEMENT_NODE) {
                        let idx = 0;
                        let sibling = element.previousSibling;
                        while (sibling) {
                            if (sibling.nodeType === Node.ELEMENT_NODE && sibling.tagName === element.tagName) idx++;
                            sibling = sibling.previousSibling;
                        }
                        const tagName = element.tagName.toLowerCase();
                        parts.unshift(`${tagName}[${idx + 1}]`);
                        element = element.parentNode;
                    }
                    return parts.length ? `/${parts.join('/')}` : '';
                }
                
                const element = getElementByXPath(xpath);
                if (!element) return null;
                
                return findFirstSVGInSubtree(element);
            }
            """
		result = await page.evaluate(script, xpath)
		return result if result else ''
	except Exception as e:
		print(f'Error finding visual marker for xpath {xpath}: {str(e)}')
		return ''
