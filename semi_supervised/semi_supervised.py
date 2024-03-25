from datetime import datetime
import logging, os

import numpy as np

logging.disable(logging.WARNING)  # disable TF logging
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import matplotlib.pyplot as plt
import pandas as pd

from utils import (
    autoencoder_predict,
    build_dataset,
    calculate_threshold,
    evaluate_model,
    extract_anomalous_data,
    model_definition,
    split_df,
)

"""
ND: Normal Data
AD: Anomalous Data
"""

YEAR = 2022
MONTH = 9
date_dataset = datetime(YEAR, MONTH, 1)

DATASET_FOLDER = "./dataset/"
DATASET_FOLDER_REBUILD = DATASET_FOLDER + "rebuild/"
dataset_rebuild_path = DATASET_FOLDER_REBUILD + date_dataset.strftime("%y-%m") + "/"

NODE = "10"

ACCEPTED_PLUGINS = ["nagios", "ganglia", "ipmi"]
NAN_THRESH_PERCENT = 0.3

RANDOM_STATE = 42
TRAIN_ND_PERC, VAL_ND_PERC, TEST_ND_PERC = 60, 10, 30
VAL_AD_PERC, TEST_AD_PERC = 30, 70

EPOCHS = 128
BATCH_SIZE = 128


def main():

    df = build_dataset(ACCEPTED_PLUGINS, NODE, dataset_rebuild_path, NAN_THRESH_PERCENT)
    print("\n-----------------------------------------------------------")
    print(df.info(verbose=True))

    df_ND_indexes, df_AD_indexes = extract_anomalous_data(df)

    # Split ND data, without "timestamp" feature
    train_ND, val_ND, test_ND = split_df(
        df.loc[df_ND_indexes].drop(columns="timestamp"),
        train=TRAIN_ND_PERC,
        val=VAL_ND_PERC,
        test=TEST_ND_PERC,
        rand=RANDOM_STATE,
    )

    # Autoencoder definition
    n_features = df.shape[1] - 1  # minus the "timestamp" feature
    history, autoencoder = model_definition(
        n_features,
        np.asarray(train_ND).astype(np.float64),  # conversion to array
        np.asarray(val_ND).astype(np.float64),  # conversion to array
        EPOCHS,
        BATCH_SIZE,
    )

    plt.plot(history.history["loss"], label="Training Loss")
    plt.plot(history.history["val_loss"], label="Validation Loss")
    plt.legend()
    plt.show()

    # Prediction of normal data
    _ = autoencoder_predict(autoencoder, train_ND, "ND train")
    decoded_test_ND = autoencoder_predict(autoencoder, test_ND, "ND test")
    decoded_val_ND = autoencoder_predict(autoencoder, val_ND, "ND val")

    # Prediction of anomalous data (without "timestamp" feature)
    decoded_AD = autoencoder_predict(autoencoder, df.loc[df_AD_indexes].drop(columns="timestamp"), "AD")

    # Split AD actual data and predicted data
    _, val_AD, test_AD = split_df(
        df.loc[df_AD_indexes].drop(columns="timestamp"),  # without "timestamp" feature
        train=0,
        val=VAL_AD_PERC,
        test=TEST_AD_PERC,
        rand=RANDOM_STATE,
    )
    _, decoded_val_AD, decoded_test_AD = split_df(
        decoded_AD,
        train=0,
        val=VAL_AD_PERC,
        test=TEST_AD_PERC,
        rand=RANDOM_STATE,
    )

    # Find best Threshold using validation sets
    threshold, _ = calculate_threshold(
        val_ND,
        decoded_val_ND,
        val_AD,
        decoded_val_AD,
    )

    # Test on unseen data
    pred_classes_test_ND, precision_test_ND, recall_test_ND, fscore_test_ND = evaluate_model(
        True, test_ND, decoded_test_ND, threshold
    )
    pred_classes_test_AD, precision_test_AD, recall_test_AD, fscore_test_AD = evaluate_model(
        False, test_AD, decoded_test_AD, threshold
    )

    print("ND TEST: precision = {} recall = {} fscore = {}".format(precision_test_ND, recall_test_ND, fscore_test_ND))
    print("AD TEST: precision = {} recall = {} fscore = {}".format(precision_test_AD, recall_test_AD, fscore_test_AD))

    # Build dataframe with predicted classes and original timestamps
    pred_classes_test_ND = pd.DataFrame(pred_classes_test_ND, index=test_ND.index)
    pred_classes_test_AD = pd.DataFrame(pred_classes_test_AD, index=test_AD.index)
    pred_classes_test = pd.concat((pred_classes_test_ND, pred_classes_test_AD), axis=0).sort_index()
    pred_classes_test["timestamp"] = df.loc[pred_classes_test.index]["timestamp"]

    # Build dataframe with original classes (nagiosdrained) and original timestamps
    classes_test = pd.DataFrame(pd.concat((test_ND, test_AD), axis=0)).sort_index()[["nagiosdrained"]]
    classes_test["timestamp"] = df.loc[classes_test.index]["timestamp"]

    plt.plot(classes_test["timestamp"], classes_test["nagiosdrained"], label="Actual classes")
    plt.plot(pred_classes_test["timestamp"], pred_classes_test[0], label="Predicted classes")
    plt.xticks(classes_test["timestamp"][::100])
    plt.xlabel("Timestamp")
    plt.xlabel("Class")
    plt.yticks([0, 1])
    plt.legend()
    plt.tick_params(axis="x", labelrotation=45)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
