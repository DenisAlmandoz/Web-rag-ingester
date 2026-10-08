# Databricks notebook source
from jobs import WebIngestion, WebIngestionConfig

WebIngestion(WebIngestionConfig.from_widgets()).run()
